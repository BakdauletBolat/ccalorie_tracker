import logging
from datetime import date, datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram import F

from google.genai.errors import ClientError, ServerError

from app.bmr import calc_bmr
from app.config import settings
from app.database import (
    bulk_create_daily_snapshots,
    clear_entries,
    delete_entry,
    get_daily_snapshot,
    get_entries,
    get_entries_range,
    get_user_active_days,
    get_user_profile,
    save_entry,
    upsert_daily_snapshot,
    upsert_user_profile,
)
from app.models import DailyProfileSnapshot, FoodEntry, NutritionData, UserProfile
from app.parser import generate_off_topic_reply, parse_food_text, parse_food_with_context, parse_intent

logger = logging.getLogger(__name__)

# Pending entries awaiting user confirmation: user_id -> list[FoodEntry]
_pending: dict[int, list[FoodEntry]] = {}

bot = Bot(token=settings.TELEGRAM_TOKEN)
dp = Dispatcher()

KEYBOARD = types.ReplyKeyboardMarkup(
    keyboard=[
        [
            types.KeyboardButton(text="🍽 Приёмы пищи"),
            types.KeyboardButton(text="📊 Неделя"),
        ],
        [
            types.KeyboardButton(text="👤 Профиль"),
        ],
    ],
    resize_keyboard=True,
)


class OnboardingStates(StatesGroup):
    waiting_gender = State()
    waiting_weight = State()
    waiting_height = State()
    waiting_age = State()


class EditProfileStates(StatesGroup):
    waiting_weight = State()
    waiting_height = State()
    waiting_age = State()


@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    logger.info("user=%s вызвал /start", user_id)
    profile = await get_user_profile(user_id)
    if profile:
        bmr = calc_bmr(profile.weight, profile.height, profile.age, profile.gender)
        name = message.from_user.first_name  # type: ignore[union-attr]
        await message.answer(
            f"👋 С возвращением, {name}!\n\n"
            f"🎯 Твой BMR: <b>{bmr:.0f}</b> ккал/день\n\n"
            "Просто напиши что ты съел, например:\n"
            "«Овсянка и банан»",
            reply_markup=KEYBOARD,
            parse_mode="HTML",
        )
        return

    # Онбординг — начинаем сбор профиля
    name = message.from_user.first_name  # type: ignore[union-attr]
    await state.set_state(OnboardingStates.waiting_gender)
    await message.answer(
        f"👋 Привет, {name}!\n\n"
        "Я — КалорийБот 🍽\n"
        "Для начала давай заполним твой профиль.\n\n"
        "Выбери пол:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [
                types.InlineKeyboardButton(text="👨 Мужской", callback_data="gender:male"),
                types.InlineKeyboardButton(text="👩 Женский", callback_data="gender:female"),
            ]
        ]),
    )


@dp.callback_query(F.data.startswith("gender:"), OnboardingStates.waiting_gender)
async def onboard_gender(callback: types.CallbackQuery, state: FSMContext) -> None:
    gender = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    await state.update_data(gender=gender)
    await state.set_state(OnboardingStates.waiting_weight)
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"✅ Пол: {'Мужской' if gender == 'male' else 'Женский'}\n\n"
        "⚖️ Введи свой вес (кг):"
    )
    await callback.answer()


@dp.message(OnboardingStates.waiting_weight)
async def onboard_weight(message: types.Message, state: FSMContext) -> None:
    try:
        weight = float(message.text.replace(",", "."))  # type: ignore[union-attr]
        assert 20 <= weight <= 300
    except (ValueError, AssertionError, TypeError):
        await message.answer("Введи корректный вес (например: 75):")
        return
    await state.update_data(weight=weight)
    await state.set_state(OnboardingStates.waiting_height)
    await message.answer(f"✅ Вес: {weight} кг\n\n📏 Введи свой рост (см):")


@dp.message(OnboardingStates.waiting_height)
async def onboard_height(message: types.Message, state: FSMContext) -> None:
    try:
        height = float(message.text.replace(",", "."))  # type: ignore[union-attr]
        assert 50 <= height <= 250
    except (ValueError, AssertionError, TypeError):
        await message.answer("Введи корректный рост (например: 175):")
        return
    await state.update_data(height=height)
    await state.set_state(OnboardingStates.waiting_age)
    await message.answer(f"✅ Рост: {height} см\n\n🎂 Введи свой возраст:")


@dp.message(OnboardingStates.waiting_age)
async def onboard_age(message: types.Message, state: FSMContext) -> None:
    try:
        age = int(message.text)  # type: ignore[union-attr]
        assert 5 <= age <= 120
    except (ValueError, AssertionError, TypeError):
        await message.answer("Введи корректный возраст (например: 25):")
        return

    data = await state.get_data()
    await state.clear()

    user_id = message.from_user.id  # type: ignore[union-attr]
    profile = UserProfile(
        user_id=user_id,
        gender=data["gender"],
        weight=data["weight"],
        height=data["height"],
        age=age,
    )
    await upsert_user_profile(profile)

    # Дневной снимок на сегодня
    await upsert_daily_snapshot(DailyProfileSnapshot(
        user_id=user_id, weight=profile.weight,
        height=profile.height, age=profile.age, date=date.today(),
    ))

    # Bulk-миграция: создать снимки для всех дней с записями еды
    active_days = await get_user_active_days(user_id)
    if active_days:
        snapshots = [
            DailyProfileSnapshot(
                user_id=user_id, weight=profile.weight,
                height=profile.height, age=profile.age, date=day,
            )
            for day in active_days
        ]
        await bulk_create_daily_snapshots(snapshots)

    bmr = calc_bmr(profile.weight, profile.height, profile.age, profile.gender)
    gender_label = "Мужской" if profile.gender == "male" else "Женский"
    await message.answer(
        f"✅ Профиль сохранён!\n\n"
        f"🚻 Пол: {gender_label}\n"
        f"⚖️ Вес: {profile.weight} кг\n"
        f"📏 Рост: {profile.height} см\n"
        f"🎂 Возраст: {profile.age}\n\n"
        f"🎯 Твой BMR: <b>{bmr:.0f}</b> ккал/день\n\n"
        "Теперь просто напиши что ты съел!",
        reply_markup=KEYBOARD,
        parse_mode="HTML",
    )


@dp.message(F.text == "👤 Профиль")
async def btn_profile(message: types.Message) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    profile = await get_user_profile(user_id)
    if not profile:
        await message.answer(
            "Профиль не найден. Нажми /start чтобы создать.",
        )
        return

    bmr = calc_bmr(profile.weight, profile.height, profile.age, profile.gender)
    gender_label = "Мужской" if profile.gender == "male" else "Женский"
    await message.answer(
        f"👤 <b>Твой профиль</b>\n\n"
        f"🚻 Пол: {gender_label}\n"
        f"⚖️ Вес: {profile.weight} кг\n"
        f"📏 Рост: {profile.height} см\n"
        f"🎂 Возраст: {profile.age}\n\n"
        f"🎯 BMR: <b>{bmr:.0f}</b> ккал/день",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="⚖️ Изменить вес", callback_data="edit:weight")],
            [types.InlineKeyboardButton(text="📏 Изменить рост", callback_data="edit:height")],
            [types.InlineKeyboardButton(text="🎂 Изменить возраст", callback_data="edit:age")],
            [types.InlineKeyboardButton(text="🚻 Изменить пол", callback_data="edit:gender")],
        ]),
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "edit:weight")
async def cb_edit_weight(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EditProfileStates.waiting_weight)
    await callback.message.edit_text("⚖️ Введи новый вес (кг):")  # type: ignore[union-attr]
    await callback.answer()


@dp.callback_query(F.data == "edit:height")
async def cb_edit_height(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EditProfileStates.waiting_height)
    await callback.message.edit_text("📏 Введи новый рост (см):")  # type: ignore[union-attr]
    await callback.answer()


@dp.callback_query(F.data == "edit:age")
async def cb_edit_age(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EditProfileStates.waiting_age)
    await callback.message.edit_text("🎂 Введи новый возраст:")  # type: ignore[union-attr]
    await callback.answer()


@dp.callback_query(F.data == "edit:gender")
async def cb_edit_gender(callback: types.CallbackQuery) -> None:
    await callback.message.edit_text(  # type: ignore[union-attr]
        "🚻 Выбери пол:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [
                types.InlineKeyboardButton(text="👨 Мужской", callback_data="setgender:male"),
                types.InlineKeyboardButton(text="👩 Женский", callback_data="setgender:female"),
            ]
        ]),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("setgender:"))
async def cb_set_gender(callback: types.CallbackQuery) -> None:
    gender = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    user_id = callback.from_user.id
    profile = await get_user_profile(user_id)
    if not profile:
        await callback.answer("Профиль не найден")
        return
    profile.gender = gender
    await upsert_user_profile(profile)
    await upsert_daily_snapshot(DailyProfileSnapshot(
        user_id=user_id, weight=profile.weight,
        height=profile.height, age=profile.age, date=date.today(),
    ))
    bmr = calc_bmr(profile.weight, profile.height, profile.age, profile.gender)
    gender_label = "Мужской" if gender == "male" else "Женский"
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"✅ Пол изменён: {gender_label}\n"
        f"🎯 BMR: <b>{bmr:.0f}</b> ккал/день",
        parse_mode="HTML",
    )
    await callback.answer()


@dp.message(EditProfileStates.waiting_weight)
async def edit_weight(message: types.Message, state: FSMContext) -> None:
    try:
        weight = float(message.text.replace(",", "."))  # type: ignore[union-attr]
        assert 20 <= weight <= 300
    except (ValueError, AssertionError, TypeError):
        await message.answer("Введи корректный вес (например: 75):")
        return
    user_id = message.from_user.id  # type: ignore[union-attr]
    profile = await get_user_profile(user_id)
    if not profile:
        await state.clear()
        await message.answer("Профиль не найден. Нажми /start.")
        return
    profile.weight = weight
    await upsert_user_profile(profile)
    await upsert_daily_snapshot(DailyProfileSnapshot(
        user_id=user_id, weight=profile.weight,
        height=profile.height, age=profile.age, date=date.today(),
    ))
    await state.clear()
    bmr = calc_bmr(profile.weight, profile.height, profile.age, profile.gender)
    await message.answer(
        f"✅ Вес изменён: {weight} кг\n"
        f"🎯 BMR: <b>{bmr:.0f}</b> ккал/день",
        reply_markup=KEYBOARD,
        parse_mode="HTML",
    )


@dp.message(EditProfileStates.waiting_height)
async def edit_height(message: types.Message, state: FSMContext) -> None:
    try:
        height = float(message.text.replace(",", "."))  # type: ignore[union-attr]
        assert 50 <= height <= 250
    except (ValueError, AssertionError, TypeError):
        await message.answer("Введи корректный рост (например: 175):")
        return
    user_id = message.from_user.id  # type: ignore[union-attr]
    profile = await get_user_profile(user_id)
    if not profile:
        await state.clear()
        await message.answer("Профиль не найден. Нажми /start.")
        return
    profile.height = height
    await upsert_user_profile(profile)
    await upsert_daily_snapshot(DailyProfileSnapshot(
        user_id=user_id, weight=profile.weight,
        height=profile.height, age=profile.age, date=date.today(),
    ))
    await state.clear()
    bmr = calc_bmr(profile.weight, profile.height, profile.age, profile.gender)
    await message.answer(
        f"✅ Рост изменён: {height} см\n"
        f"🎯 BMR: <b>{bmr:.0f}</b> ккал/день",
        reply_markup=KEYBOARD,
        parse_mode="HTML",
    )


@dp.message(EditProfileStates.waiting_age)
async def edit_age(message: types.Message, state: FSMContext) -> None:
    try:
        age = int(message.text)  # type: ignore[union-attr]
        assert 5 <= age <= 120
    except (ValueError, AssertionError, TypeError):
        await message.answer("Введи корректный возраст (например: 25):")
        return
    user_id = message.from_user.id  # type: ignore[union-attr]
    profile = await get_user_profile(user_id)
    if not profile:
        await state.clear()
        await message.answer("Профиль не найден. Нажми /start.")
        return
    profile.age = age
    await upsert_user_profile(profile)
    await upsert_daily_snapshot(DailyProfileSnapshot(
        user_id=user_id, weight=profile.weight,
        height=profile.height, age=profile.age, date=date.today(),
    ))
    await state.clear()
    bmr = calc_bmr(profile.weight, profile.height, profile.age, profile.gender)
    await message.answer(
        f"✅ Возраст изменён: {age}\n"
        f"🎯 BMR: <b>{bmr:.0f}</b> ккал/день",
        reply_markup=KEYBOARD,
        parse_mode="HTML",
    )


async def _ensure_daily_snapshot(user_id: int) -> DailyProfileSnapshot | None:
    """Создаёт снимок на сегодня если его нет. Возвращает снимок или None."""
    snapshot = await get_daily_snapshot(user_id, date.today())
    if snapshot:
        return snapshot
    profile = await get_user_profile(user_id)
    if not profile:
        return None
    snapshot = DailyProfileSnapshot(
        user_id=user_id, weight=profile.weight,
        height=profile.height, age=profile.age, date=date.today(),
    )
    await upsert_daily_snapshot(snapshot)
    return snapshot


async def _show_history(message: types.Message, day: date | None = None) -> None:
    day = day or date.today()
    logger.info("user=%s запросил историю за %s", message.from_user.id, day)  # type: ignore[union-attr]
    entries = await get_entries(message.from_user.id, day)  # type: ignore[union-attr]
    if not entries:
        await message.answer(f"Записей за {day.strftime('%d.%m.%Y')} нет.")
        return

    day_str = day.isoformat()
    total = NutritionData(calories=0, protein=0, fat=0, carbs=0)
    buttons: list[list[types.InlineKeyboardButton]] = []
    for i, (entry_id, e) in enumerate(entries, 1):
        buttons.append([
            types.InlineKeyboardButton(
                text=f"{i}. {e.description} — {e.nutrition.calories:.0f} ккал",
                callback_data=f"view:{entry_id}:{day_str}",
            )
        ])
        total.calories += e.nutrition.calories
        total.protein += e.nutrition.protein
        total.fat += e.nutrition.fat
        total.carbs += e.nutrition.carbs

    label = "Сегодня" if day == date.today() else day.strftime('%d.%m.%Y')
    text = (
        f"📅 <b>{label}</b>\n\n"
        f"🔥 Калории: <b>{total.calories:.0f}</b> ккал\n"
        f"🥩 Белки: <b>{total.protein:.0f}</b> г\n"
        f"🧈 Жиры: <b>{total.fat:.0f}</b> г\n"
        f"🍞 Углеводы: <b>{total.carbs:.0f}</b> г\n"
    )

    # Дефицит калорий
    snapshot = await get_daily_snapshot(message.from_user.id, day)  # type: ignore[union-attr]
    if snapshot:
        profile = await get_user_profile(message.from_user.id)  # type: ignore[union-attr]
        if profile:
            bmr = calc_bmr(snapshot.weight, snapshot.height, snapshot.age, profile.gender)
            diff = total.calories - bmr
            if diff <= 0:
                text += f"\n🎯 BMR: {bmr:.0f} ккал\n📉 Осталось: <b>{abs(diff):.0f}</b> ккал"
            else:
                text += f"\n🎯 BMR: {bmr:.0f} ккал\n📈 Сверх нормы: <b>{diff:.0f}</b> ккал"

    text += f"\n\nЗаписей: {len(entries)} — нажми чтобы посмотреть подробнее:"
    await message.answer(
        text,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("view:"))
async def cb_view(callback: types.CallbackQuery) -> None:
    # format: view:<entry_id>:<date>
    parts = callback.data.split(":", 2)  # type: ignore[union-attr]
    entry_id = parts[1]
    day = date.fromisoformat(parts[2]) if len(parts) > 2 else date.today()
    entries = await get_entries(callback.from_user.id, day)
    entry: FoodEntry | None = None
    for eid, e in entries:
        if eid == entry_id:
            entry = e
            break

    if not entry:
        await callback.answer("Запись не найдена")
        return

    text = (
        f"🍽 <b>{entry.description}</b>\n\n"
        f"🔥 Калории: {entry.nutrition.calories:.0f} ккал\n"
        f"🥩 Белки: {entry.nutrition.protein:.0f} г\n"
        f"🧈 Жиры: {entry.nutrition.fat:.0f} г\n"
        f"🍞 Углеводы: {entry.nutrition.carbs:.0f} г\n\n"
        f"🕐 {entry.created_at.strftime('%H:%M')}"
    )
    day_str = day.isoformat()
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="❌ Удалить", callback_data=f"del:{entry_id}:{day_str}")],
        [types.InlineKeyboardButton(text="◀️ Назад", callback_data=f"back:{day_str}")],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")  # type: ignore[union-attr]
    await callback.answer()


@dp.callback_query(F.data.startswith("del:"))
async def cb_delete(callback: types.CallbackQuery) -> None:
    # format: del:<entry_id>:<date>
    parts = callback.data.split(":", 2)  # type: ignore[union-attr]
    entry_id = parts[1]
    day = date.fromisoformat(parts[2]) if len(parts) > 2 else date.today()
    deleted = await delete_entry(entry_id, callback.from_user.id)
    if not deleted:
        await callback.answer("Запись не найдена")
        return

    await callback.answer("Запись удалена")
    entries = await get_entries(callback.from_user.id, day)
    if not entries:
        label = "Сегодня" if day == date.today() else day.strftime('%d.%m.%Y')
        await callback.message.edit_text(f"Записей за {label} нет.")  # type: ignore[union-attr]
        return
    await _edit_history(callback.message, entries, day, callback.from_user.id)  # type: ignore[arg-type]


@dp.callback_query(F.data.startswith("back:"))
async def cb_back(callback: types.CallbackQuery) -> None:
    day_str = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    day = date.fromisoformat(day_str)
    entries = await get_entries(callback.from_user.id, day)
    if not entries:
        label = "Сегодня" if day == date.today() else day.strftime('%d.%m.%Y')
        await callback.message.edit_text(f"Записей за {label} нет.")  # type: ignore[union-attr]
        await callback.answer()
        return
    await _edit_history(callback.message, entries, day, callback.from_user.id)  # type: ignore[arg-type]
    await callback.answer()


async def _edit_history(message: types.Message, entries: list[tuple[str, FoodEntry]], day: date, user_id: int) -> None:
    day_str = day.isoformat()
    total = NutritionData(calories=0, protein=0, fat=0, carbs=0)
    buttons: list[list[types.InlineKeyboardButton]] = []
    for i, (entry_id, e) in enumerate(entries, 1):
        buttons.append([
            types.InlineKeyboardButton(
                text=f"{i}. {e.description} — {e.nutrition.calories:.0f} ккал",
                callback_data=f"view:{entry_id}:{day_str}",
            )
        ])
        total.calories += e.nutrition.calories
        total.protein += e.nutrition.protein
        total.fat += e.nutrition.fat
        total.carbs += e.nutrition.carbs

    label = "Сегодня" if day == date.today() else day.strftime('%d.%m.%Y')
    text = (
        f"📅 <b>{label}</b>\n\n"
        f"🔥 Калории: <b>{total.calories:.0f}</b> ккал\n"
        f"🥩 Белки: <b>{total.protein:.0f}</b> г\n"
        f"🧈 Жиры: <b>{total.fat:.0f}</b> г\n"
        f"🍞 Углеводы: <b>{total.carbs:.0f}</b> г\n"
    )

    snapshot = await get_daily_snapshot(user_id, day)
    if snapshot:
        profile = await get_user_profile(user_id)
        if profile:
            bmr = calc_bmr(snapshot.weight, snapshot.height, snapshot.age, profile.gender)
            diff = total.calories - bmr
            if diff <= 0:
                text += f"\n🎯 BMR: {bmr:.0f} ккал\n📉 Осталось: <b>{abs(diff):.0f}</b> ккал"
            else:
                text += f"\n🎯 BMR: {bmr:.0f} ккал\n📈 Сверх нормы: <b>{diff:.0f}</b> ккал"

    text += f"\n\nЗаписей: {len(entries)} — нажми чтобы посмотреть подробнее:"
    await message.edit_text(
        text,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


async def _do_clear(message: types.Message) -> None:
    logger.info("user=%s вызвал очистку", message.from_user.id)  # type: ignore[union-attr]
    deleted = await clear_entries(message.from_user.id, date.today())  # type: ignore[union-attr]
    if deleted:
        await message.answer(f"Удалено {deleted} записей за сегодня.")
    else:
        await message.answer("Сегодня записей нет.")


@dp.message(Command("history"))
async def cmd_history(message: types.Message) -> None:
    await _show_history(message)


@dp.message(F.text == "🍽 Приёмы пищи")
async def btn_today(message: types.Message) -> None:
    await _show_history(message)


@dp.message(Command("clear"))
async def cmd_clear(message: types.Message) -> None:
    await _do_clear(message)


def _week_bounds(ref: date) -> tuple[date, date]:
    start = ref - timedelta(days=ref.weekday())  # Monday
    end = start + timedelta(days=6)  # Sunday
    return start, end


WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


async def _build_week_report(user_id: int, ref: date) -> tuple[str, types.InlineKeyboardMarkup]:
    start, end = _week_bounds(ref)
    entries = await get_entries_range(user_id, start, end)
    profile = await get_user_profile(user_id)

    # Group by day
    daily: dict[date, NutritionData] = {}
    for _, e in entries:
        day = e.created_at.date()
        if day not in daily:
            daily[day] = NutritionData(calories=0, protein=0, fat=0, carbs=0)
        daily[day].calories += e.nutrition.calories
        daily[day].protein += e.nutrition.protein
        daily[day].fat += e.nutrition.fat
        daily[day].carbs += e.nutrition.carbs

    # Собираем снимки для дней с записями (для BMR)
    snapshots: dict[date, DailyProfileSnapshot] = {}
    if profile:
        for day in daily:
            snap = await get_daily_snapshot(user_id, day)
            if snap:
                snapshots[day] = snap

    lines: list[str] = []
    week_total = NutritionData(calories=0, protein=0, fat=0, carbs=0)
    total_deficit = 0.0
    days_with_bmr = 0

    for i in range(7):
        day = start + timedelta(days=i)
        label = f"{WEEKDAYS[i]} {day.strftime('%d.%m')}"
        if day == date.today():
            label = f"<b>{label} (сегодня)</b>"
        n = daily.get(day)
        if n:
            line = (
                f"{label} — {n.calories:.0f} ккал | "
                f"{n.protein:.0f}Б {n.fat:.0f}Ж {n.carbs:.0f}У"
            )
            snap = snapshots.get(day)
            if snap and profile:
                bmr = calc_bmr(snap.weight, snap.height, snap.age, profile.gender)
                diff = n.calories - bmr
                total_deficit += diff
                days_with_bmr += 1
                if diff <= 0:
                    line += f" | 📉 {diff:.0f}"
                else:
                    line += f" | 📈 +{diff:.0f}"
            lines.append(line)
            week_total.calories += n.calories
            week_total.protein += n.protein
            week_total.fat += n.fat
            week_total.carbs += n.carbs
        else:
            lines.append(f"{label} — нет записей")

    text = (
        f"📊 <b>Неделя {start.strftime('%d.%m')} – {end.strftime('%d.%m.%Y')}</b>\n\n"
        + "\n".join(lines)
        + f"\n\n<b>Итого за неделю:</b>\n"
        f"🔥 {week_total.calories:.0f} ккал | "
        f"🥩 {week_total.protein:.0f} Б | "
        f"🧈 {week_total.fat:.0f} Ж | "
        f"🍞 {week_total.carbs:.0f} У"
    )

    if days_with_bmr > 0:
        avg_deficit = total_deficit / days_with_bmr
        if avg_deficit <= 0:
            text += f"\n\n📉 Средний дефицит: <b>{abs(avg_deficit):.0f}</b> ккал/день"
        else:
            text += f"\n\n📈 Средний профицит: <b>{avg_deficit:.0f}</b> ккал/день"

    prev_week = (start - timedelta(days=7)).isoformat()
    next_week = (start + timedelta(days=7)).isoformat()
    buttons: list[list[types.InlineKeyboardButton]] = [[
        types.InlineKeyboardButton(text="◀️ Назад", callback_data=f"week:{prev_week}"),
        types.InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"week:{next_week}"),
    ]]
    return text, types.InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.message(F.text == "📊 Неделя")
async def btn_week(message: types.Message) -> None:
    text, keyboard = await _build_week_report(message.from_user.id, date.today())  # type: ignore[union-attr]
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@dp.callback_query(F.data.startswith("week:"))
async def cb_week(callback: types.CallbackQuery) -> None:
    ref = date.fromisoformat(callback.data.split(":", 1)[1])  # type: ignore[union-attr]
    text, keyboard = await _build_week_report(callback.from_user.id, ref)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")  # type: ignore[union-attr]
    await callback.answer()


def _build_pending_text(entries: list[FoodEntry]) -> str:
    total = NutritionData(calories=0, protein=0, fat=0, carbs=0)
    lines: list[str] = []
    for i, e in enumerate(entries, 1):
        lines.append(f"{i}. {e.description} — {e.nutrition.calories:.0f} ккал")
        total.calories += e.nutrition.calories
        total.protein += e.nutrition.protein
        total.fat += e.nutrition.fat
        total.carbs += e.nutrition.carbs

    items_text = "\n".join(lines)
    return (
        f"🍽 <b>Приём пищи</b>\n\n"
        f"{items_text}\n\n"
        f"<b>Итого:</b>\n"
        f"🔥 {total.calories:.0f} ккал | "
        f"🥩 {total.protein:.0f} Б | "
        f"🧈 {total.fat:.0f} Ж | "
        f"🍞 {total.carbs:.0f} У\n\n"
        f"Добавь ещё продукт, измени список или подтверди:"
    )


def _build_pending_keyboard(entries: list[FoodEntry]) -> types.InlineKeyboardMarkup:
    buttons: list[list[types.InlineKeyboardButton]] = []
    for i, e in enumerate(entries):
        buttons.append([
            types.InlineKeyboardButton(
                text=f"❌ {i + 1}. {e.description}",
                callback_data=f"pdel:{i}",
            )
        ])
    buttons.append([
        types.InlineKeyboardButton(text="✅ Записать", callback_data="confirm"),
        types.InlineKeyboardButton(text="🚫 Отмена", callback_data="cancel"),
    ])
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.callback_query(F.data.startswith("pdel:"))
async def cb_pending_delete(callback: types.CallbackQuery) -> None:
    user_id = callback.from_user.id
    index = int(callback.data.split(":", 1)[1])  # type: ignore[union-attr]
    entries = _pending.get(user_id)
    if not entries or index >= len(entries):
        await callback.answer("Не найдено")
        return

    removed = entries.pop(index)
    logger.info("user=%s убрал из pending: %s", user_id, removed.description)

    if not entries:
        _pending.pop(user_id, None)
        await callback.message.edit_text("Список очищен.")  # type: ignore[union-attr]
        await callback.answer()
        return

    await callback.message.edit_text(  # type: ignore[union-attr]
        _build_pending_text(entries),
        reply_markup=_build_pending_keyboard(entries),
        parse_mode="HTML",
    )
    await callback.answer(f"Убрано: {removed.description}")


@dp.callback_query(F.data == "confirm")
async def cb_confirm(callback: types.CallbackQuery) -> None:
    user_id = callback.from_user.id
    entries = _pending.pop(user_id, None)
    if not entries:
        await callback.answer("Нет записей для сохранения")
        return

    for entry in entries:
        await save_entry(entry)
    logger.info("user=%s подтвердил %d записей", user_id, len(entries))

    total = NutritionData(calories=0, protein=0, fat=0, carbs=0)
    lines: list[str] = []
    for i, e in enumerate(entries, 1):
        lines.append(f"{i}. {e.description} — {e.nutrition.calories:.0f} ккал")
        total.calories += e.nutrition.calories
        total.protein += e.nutrition.protein
        total.fat += e.nutrition.fat
        total.carbs += e.nutrition.carbs

    text = (
        f"✅ <b>Записано!</b>\n\n"
        f"{chr(10).join(lines)}\n\n"
        f"🔥 {total.calories:.0f} ккал | "
        f"🥩 {total.protein:.0f} Б | "
        f"🧈 {total.fat:.0f} Ж | "
        f"🍞 {total.carbs:.0f} У"
    )
    await callback.message.edit_text(text, parse_mode="HTML")  # type: ignore[union-attr]
    await callback.answer("Записано!")


@dp.callback_query(F.data == "cancel")
async def cb_cancel(callback: types.CallbackQuery) -> None:
    user_id = callback.from_user.id
    _pending.pop(user_id, None)
    logger.info("user=%s отменил pending", user_id)
    await callback.message.edit_text("🚫 Отменено.")  # type: ignore[union-attr]
    await callback.answer()


@dp.message()
async def handle_food(message: types.Message) -> None:
    if not message.text:
        return

    user_id = message.from_user.id  # type: ignore[union-attr]
    logger.info("user=%s отправил текст: %s", user_id, message.text)

    # Автоснимок профиля при первом сообщении за день
    await _ensure_daily_snapshot(user_id)

    # If user has pending entries, skip intent detection — treat as food context update
    if user_id in _pending:
        await message.answer("Обрабатываю...")
        current_descriptions = [e.description for e in _pending[user_id]]
        try:
            items = await parse_food_with_context(message.text, current_descriptions)
        except (ServerError, ClientError):
            logger.warning("Gemini ошибка для user=%s", user_id)
            await message.answer("Сервис перегружен, попробуйте через 30 секунд.")
            return

        _pending[user_id] = [
            FoodEntry(
                user_id=user_id,
                description=p.description,
                nutrition=NutritionData(
                    calories=p.calories, protein=p.protein,
                    fat=p.fat, carbs=p.carbs,
                ),
                created_at=datetime.now(),
            )
            for p in items
        ]
        await message.answer(
            _build_pending_text(_pending[user_id]),
            reply_markup=_build_pending_keyboard(_pending[user_id]),
            parse_mode="HTML",
        )
        return

    try:
        intent = await parse_intent(message.text)
    except (ServerError, ClientError):
        logger.warning("Gemini ошибка для user=%s", user_id)
        await message.answer("Сервис перегружен, попробуйте через 30 секунд.")
        return

    if intent.intent == "history":
        day = date.fromisoformat(intent.date) if intent.date else date.today()
        await _show_history(message, day)
        return

    if intent.intent == "other":
        try:
            reply = await generate_off_topic_reply(message.text)
            await message.answer(reply)
        except (ServerError, ClientError):
            await message.answer("Я умею записывать еду и показывать историю питания 🍽")
        return

    await message.answer("Обрабатываю...")

    try:
        parsed = await parse_food_text(message.text)
    except (ServerError, ClientError):
        logger.warning("Gemini ошибка для user=%s", user_id)
        await message.answer("Сервис перегружен, попробуйте через 30 секунд.")
        return

    entry = FoodEntry(
        user_id=user_id,
        description=parsed.description,
        nutrition=NutritionData(
            calories=parsed.calories, protein=parsed.protein,
            fat=parsed.fat, carbs=parsed.carbs,
        ),
        created_at=datetime.now(),
    )
    _pending[user_id] = [entry]
    logger.info("user=%s pending: %s", user_id, entry.description)

    await message.answer(
        _build_pending_text(_pending[user_id]),
        reply_markup=_build_pending_keyboard(_pending[user_id]),
        parse_mode="HTML",
    )
