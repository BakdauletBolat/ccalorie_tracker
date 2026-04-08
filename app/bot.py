import logging
from datetime import date, datetime

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram import F

from google.genai.errors import ClientError, ServerError

from app.config import settings
from app.database import clear_entries, delete_entry, get_entries, save_entry
from app.models import FoodEntry, NutritionData
from app.parser import generate_off_topic_reply, parse_food_text, parse_intent

logger = logging.getLogger(__name__)

bot = Bot(token=settings.TELEGRAM_TOKEN)
dp = Dispatcher()

KEYBOARD = types.ReplyKeyboardMarkup(
    keyboard=[
        [
            types.KeyboardButton(text="📋 История"),
            types.KeyboardButton(text="🗑 Очистить"),
        ]
    ],
    resize_keyboard=True,
)


@dp.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    logger.info("user=%s вызвал /start", message.from_user.id)  # type: ignore[union-attr]
    name = message.from_user.first_name  # type: ignore[union-attr]
    await message.answer(
        f"👋 Привет, {name}!\n\n"
        "Я — КалорийБот 🍽\n"
        "Веду учёт твоего питания.\n\n"
        "Просто напиши что ты съел, например:\n"
        "«Завтрак: овсянка и банан, 350 ккал, 12г белка»\n\n"
        "📋 История — посмотреть записи за сегодня\n"
        "🗑 Очистить — удалить записи за сегодня",
        reply_markup=KEYBOARD,
    )


async def _show_history(message: types.Message, day: date | None = None) -> None:
    day = day or date.today()
    logger.info("user=%s запросил историю за %s", message.from_user.id, day)  # type: ignore[union-attr]
    entries = await get_entries(message.from_user.id, day)  # type: ignore[union-attr]
    if not entries:
        await message.answer(f"Записей за {day.strftime('%d.%m.%Y')} нет.")
        return

    total = NutritionData(calories=0, protein=0, fat=0, carbs=0)
    buttons: list[list[types.InlineKeyboardButton]] = []
    for i, (entry_id, e) in enumerate(entries, 1):
        buttons.append([
            types.InlineKeyboardButton(
                text=f"{i}. {e.description} — {e.nutrition.calories:.0f} ккал",
                callback_data=f"view:{entry_id}",
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
        f"🍞 Углеводы: <b>{total.carbs:.0f}</b> г\n\n"
        f"Записей: {len(entries)} — нажми чтобы посмотреть подробнее:"
    )
    await message.answer(
        text,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("view:"))
async def cb_view(callback: types.CallbackQuery) -> None:
    entry_id = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    entries = await get_entries(callback.from_user.id, date.today())
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
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="❌ Удалить", callback_data=f"del:{entry_id}")],
        [types.InlineKeyboardButton(text="◀️ Назад", callback_data="back")],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")  # type: ignore[union-attr]
    await callback.answer()


@dp.callback_query(F.data.startswith("del:"))
async def cb_delete(callback: types.CallbackQuery) -> None:
    entry_id = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    deleted = await delete_entry(entry_id, callback.from_user.id)
    if not deleted:
        await callback.answer("Запись не найдена")
        return

    await callback.answer("Запись удалена")
    # показываем обновлённую историю в том же сообщении
    entries = await get_entries(callback.from_user.id, date.today())
    if not entries:
        await callback.message.edit_text("Сегодня записей нет.")  # type: ignore[union-attr]
        return
    await _edit_history(callback.message, entries)  # type: ignore[arg-type]


@dp.callback_query(F.data == "back")
async def cb_back(callback: types.CallbackQuery) -> None:
    entries = await get_entries(callback.from_user.id, date.today())
    if not entries:
        await callback.message.edit_text("Сегодня записей нет.")  # type: ignore[union-attr]
        await callback.answer()
        return
    await _edit_history(callback.message, entries)  # type: ignore[arg-type]
    await callback.answer()


async def _edit_history(message: types.Message, entries: list[tuple[str, FoodEntry]]) -> None:
    total = NutritionData(calories=0, protein=0, fat=0, carbs=0)
    buttons: list[list[types.InlineKeyboardButton]] = []
    for i, (entry_id, e) in enumerate(entries, 1):
        buttons.append([
            types.InlineKeyboardButton(
                text=f"{i}. {e.description} — {e.nutrition.calories:.0f} ккал",
                callback_data=f"view:{entry_id}",
            )
        ])
        total.calories += e.nutrition.calories
        total.protein += e.nutrition.protein
        total.fat += e.nutrition.fat
        total.carbs += e.nutrition.carbs

    text = (
        f"📅 <b>{date.today().strftime('%d.%m.%Y')}</b>\n\n"
        f"🔥 Калории: <b>{total.calories:.0f}</b> ккал\n"
        f"🥩 Белки: <b>{total.protein:.0f}</b> г\n"
        f"🧈 Жиры: <b>{total.fat:.0f}</b> г\n"
        f"🍞 Углеводы: <b>{total.carbs:.0f}</b> г\n\n"
        f"Записей: {len(entries)} — нажми чтобы посмотреть подробнее:"
    )
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


@dp.message(F.text == "📋 История")
async def btn_history(message: types.Message) -> None:
    await _show_history(message)


@dp.message(Command("clear"))
async def cmd_clear(message: types.Message) -> None:
    await _do_clear(message)


@dp.message(F.text == "🗑 Очистить")
async def btn_clear(message: types.Message) -> None:
    await _do_clear(message)


@dp.message()
async def handle_food(message: types.Message) -> None:
    if not message.text:
        return

    logger.info("user=%s отправил текст: %s", message.from_user.id, message.text)  # type: ignore[union-attr]

    try:
        intent = await parse_intent(message.text)
    except (ServerError, ClientError):
        logger.warning("Gemini ошибка для user=%s", message.from_user.id)  # type: ignore[union-attr]
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
        logger.warning("Gemini ошибка для user=%s", message.from_user.id)  # type: ignore[union-attr]
        await message.answer("Сервис перегружен, попробуйте через 30 секунд.")
        return

    entry = FoodEntry(
        user_id=message.from_user.id,  # type: ignore[union-attr]
        description=parsed.description,
        nutrition=NutritionData(
            calories=parsed.calories,
            protein=parsed.protein,
            fat=parsed.fat,
            carbs=parsed.carbs,
        ),
        created_at=datetime.now(),
    )
    await save_entry(entry)
    logger.info("user=%s записано: %s | %s", message.from_user.id, entry.description, entry.nutrition)  # type: ignore[union-attr]

    await message.answer(
        f"✅ <b>{entry.description}</b>\n\n"
        f"🔥 Калории: {entry.nutrition.calories:.0f} ккал\n"
        f"🥩 Белки: {entry.nutrition.protein:.0f} г\n"
        f"🧈 Жиры: {entry.nutrition.fat:.0f} г\n"
        f"🍞 Углеводы: {entry.nutrition.carbs:.0f} г",
        parse_mode="HTML",
    )
