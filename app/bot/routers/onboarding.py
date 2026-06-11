import logging

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.bot import texts
from app.bot.keyboards import MAIN_KEYBOARD, activity_keyboard, gender_keyboard, goal_keyboard
from app.models import UserProfile
from app.services import ProfileService
from app.services.nutrition import ACTIVITY_LABELS, GOAL_LABELS

logger = logging.getLogger(__name__)

router = Router(name="onboarding")


class OnboardingStates(StatesGroup):
    waiting_gender = State()
    waiting_weight = State()
    waiting_height = State()
    waiting_age = State()
    waiting_activity = State()
    waiting_goal = State()


@router.message(Command("start"))
async def cmd_start(
    message: types.Message, state: FSMContext, profile_service: ProfileService,
) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    logger.info("user=%s вызвал /start", user_id)
    name = message.from_user.first_name  # type: ignore[union-attr]

    profile = await profile_service.get(user_id)
    if profile:
        # Профиль без активности/цели — дозаполняем
        if profile.activity_level is None or profile.goal is None:
            await state.set_state(OnboardingStates.waiting_activity)
            await message.answer(
                f"👋 С возвращением, {name}!\n\n"
                "Я научился считать твою дневную норму калорий 🎯\n"
                "Для этого выбери свой уровень активности:",
                reply_markup=activity_keyboard("activity"),
            )
            return

        await message.answer(
            f"👋 С возвращением, {name}!\n\n"
            f"{texts.target_line(profile)}\n\n"
            "Просто напиши что ты съел, например:\n"
            "«Овсянка и банан»",
            reply_markup=MAIN_KEYBOARD,
            parse_mode="HTML",
        )
        return

    await state.set_state(OnboardingStates.waiting_gender)
    await message.answer(
        f"👋 Привет, {name}!\n\n"
        "Я — CALorie Tracker 🍽\n"
        "Для начала давай заполним твой профиль.\n\n"
        "Выбери пол:",
        reply_markup=gender_keyboard("gender"),
    )


@router.callback_query(F.data.startswith("gender:"), OnboardingStates.waiting_gender)
async def onboard_gender(callback: types.CallbackQuery, state: FSMContext) -> None:
    gender = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    await state.update_data(gender=gender)
    await state.set_state(OnboardingStates.waiting_weight)
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"✅ Пол: {texts.gender_label(gender)}\n\n"
        "⚖️ Введи свой вес (кг):"
    )
    await callback.answer()


@router.message(OnboardingStates.waiting_weight)
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


@router.message(OnboardingStates.waiting_height)
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


@router.message(OnboardingStates.waiting_age)
async def onboard_age(message: types.Message, state: FSMContext) -> None:
    try:
        age = int(message.text)  # type: ignore[union-attr]
        assert 5 <= age <= 120
    except (ValueError, AssertionError, TypeError):
        await message.answer("Введи корректный возраст (например: 25):")
        return

    await state.update_data(age=age)
    await state.set_state(OnboardingStates.waiting_activity)
    await message.answer(
        f"✅ Возраст: {age}\n\n"
        "🏃 Выбери уровень активности:",
        reply_markup=activity_keyboard("activity"),
    )


@router.callback_query(F.data.startswith("activity:"), OnboardingStates.waiting_activity)
async def onboard_activity(callback: types.CallbackQuery, state: FSMContext) -> None:
    activity = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    await state.update_data(activity_level=activity)
    await state.set_state(OnboardingStates.waiting_goal)
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"✅ Активность: {ACTIVITY_LABELS[activity]}\n\n"
        "🎯 Выбери цель:",
        reply_markup=goal_keyboard("goal"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("goal:"), OnboardingStates.waiting_goal)
async def onboard_goal(
    callback: types.CallbackQuery, state: FSMContext, profile_service: ProfileService,
) -> None:
    goal = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    data = await state.get_data()
    await state.clear()

    user_id = callback.from_user.id
    profile = await profile_service.get(user_id)
    if profile:
        # Дозаполнение существующего профиля
        profile.activity_level = data["activity_level"]
        profile.goal = goal
        await profile_service.update(profile)
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"✅ Готово!\n\n"
            f"🏃 Активность: {ACTIVITY_LABELS[profile.activity_level]}\n"
            f"🎯 Цель: {GOAL_LABELS[goal]}\n\n"
            f"{texts.target_line(profile)}",
            parse_mode="HTML",
        )
        await callback.answer()
        return

    profile = UserProfile(
        user_id=user_id,
        gender=data["gender"],
        weight=data["weight"],
        height=data["height"],
        age=data["age"],
        activity_level=data["activity_level"],
        goal=goal,
    )
    await profile_service.create(profile)

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"✅ Профиль сохранён!\n\n"
        f"🚻 Пол: {texts.gender_label(profile.gender)}\n"
        f"⚖️ Вес: {profile.weight} кг\n"
        f"📏 Рост: {profile.height} см\n"
        f"🎂 Возраст: {profile.age}\n"
        f"🏃 Активность: {ACTIVITY_LABELS[profile.activity_level]}\n"  # type: ignore[index]
        f"🎯 Цель: {GOAL_LABELS[goal]}\n\n"
        f"{texts.target_line(profile)}",
        parse_mode="HTML",
    )
    await callback.message.answer(  # type: ignore[union-attr]
        "Теперь просто напиши что ты съел!",
        reply_markup=MAIN_KEYBOARD,
    )
    await callback.answer()
