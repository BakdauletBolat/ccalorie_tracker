import logging

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.bot import texts
from app.bot.keyboards import (
    MAIN_KEYBOARD,
    activity_keyboard,
    gender_keyboard,
    goal_keyboard,
    profile_edit_keyboard,
    timezone_keyboard,
)
from app.services import ProfileService
from app.services import time_service
from app.services.nutrition import ACTIVITY_LABELS, GOAL_LABELS, calc_bmr

logger = logging.getLogger(__name__)

router = Router(name="profile")


class EditProfileStates(StatesGroup):
    waiting_weight = State()
    waiting_height = State()
    waiting_age = State()


@router.message(F.text == "👤 Профиль")
async def btn_profile(message: types.Message, profile_service: ProfileService) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    profile = await profile_service.get(user_id)
    if not profile:
        await message.answer("Профиль не найден. Нажми /start чтобы создать.")
        return

    await message.answer(
        texts.profile_text(profile),
        reply_markup=profile_edit_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "edit:weight")
async def cb_edit_weight(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EditProfileStates.waiting_weight)
    await callback.message.edit_text("⚖️ Введи новый вес (кг):")  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data == "edit:height")
async def cb_edit_height(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EditProfileStates.waiting_height)
    await callback.message.edit_text("📏 Введи новый рост (см):")  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data == "edit:age")
async def cb_edit_age(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EditProfileStates.waiting_age)
    await callback.message.edit_text("🎂 Введи новый возраст:")  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data == "edit:gender")
async def cb_edit_gender(callback: types.CallbackQuery) -> None:
    await callback.message.edit_text(  # type: ignore[union-attr]
        "🚻 Выбери пол:",
        reply_markup=gender_keyboard("setgender"),
    )
    await callback.answer()


@router.callback_query(F.data == "edit:activity")
async def cb_edit_activity(callback: types.CallbackQuery) -> None:
    await callback.message.edit_text(  # type: ignore[union-attr]
        "🏃 Выбери уровень активности:",
        reply_markup=activity_keyboard("setactivity"),
    )
    await callback.answer()


@router.callback_query(F.data == "edit:goal")
async def cb_edit_goal(callback: types.CallbackQuery) -> None:
    await callback.message.edit_text(  # type: ignore[union-attr]
        "🎯 Выбери цель:",
        reply_markup=goal_keyboard("setgoal"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("setactivity:"))
async def cb_set_activity(callback: types.CallbackQuery, profile_service: ProfileService) -> None:
    activity = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    profile = await profile_service.get(callback.from_user.id)
    if not profile:
        await callback.answer("Профиль не найден")
        return
    profile.activity_level = activity
    await profile_service.update(profile)
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"✅ Активность изменена: {ACTIVITY_LABELS[activity]}\n"
        f"{texts.target_line(profile)}",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("setgoal:"))
async def cb_set_goal(callback: types.CallbackQuery, profile_service: ProfileService) -> None:
    goal = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    profile = await profile_service.get(callback.from_user.id)
    if not profile:
        await callback.answer("Профиль не найден")
        return
    profile.goal = goal
    await profile_service.update(profile)
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"✅ Цель изменена: {GOAL_LABELS[goal]}\n"
        f"{texts.target_line(profile)}",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "edit:timezone")
async def cb_edit_timezone(callback: types.CallbackQuery) -> None:
    await callback.message.edit_text(  # type: ignore[union-attr]
        "🌍 Выбери часовой пояс:",
        reply_markup=timezone_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settz:"))
async def cb_set_timezone(callback: types.CallbackQuery, profile_service: ProfileService) -> None:
    tz_name = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    user_id = callback.from_user.id
    profile = await profile_service.get(user_id)
    if not profile:
        await callback.answer("Профиль не найден")
        return
    profile.timezone = tz_name
    await profile_service.update(profile)
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"✅ Часовой пояс изменён: {time_service.tz_label(tz_name)}",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("setgender:"))
async def cb_set_gender(callback: types.CallbackQuery, profile_service: ProfileService) -> None:
    gender = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    user_id = callback.from_user.id
    profile = await profile_service.get(user_id)
    if not profile:
        await callback.answer("Профиль не найден")
        return
    profile.gender = gender
    await profile_service.update(profile)
    bmr = calc_bmr(profile.weight, profile.height, profile.age, profile.gender)
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"✅ Пол изменён: {texts.gender_label(gender)}\n"
        f"🎯 BMR: <b>{bmr:.0f}</b> ккал/день",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(EditProfileStates.waiting_weight)
async def edit_weight(
    message: types.Message, state: FSMContext, profile_service: ProfileService,
) -> None:
    try:
        weight = float(message.text.replace(",", "."))  # type: ignore[union-attr]
        assert 20 <= weight <= 300
    except (ValueError, AssertionError, TypeError):
        await message.answer("Введи корректный вес (например: 75):")
        return
    user_id = message.from_user.id  # type: ignore[union-attr]
    profile = await profile_service.get(user_id)
    if not profile:
        await state.clear()
        await message.answer("Профиль не найден. Нажми /start.")
        return
    profile.weight = weight
    await profile_service.update(profile)
    await state.clear()
    bmr = calc_bmr(profile.weight, profile.height, profile.age, profile.gender)
    await message.answer(
        f"✅ Вес изменён: {weight} кг\n"
        f"🎯 BMR: <b>{bmr:.0f}</b> ккал/день",
        reply_markup=MAIN_KEYBOARD,
        parse_mode="HTML",
    )


@router.message(EditProfileStates.waiting_height)
async def edit_height(
    message: types.Message, state: FSMContext, profile_service: ProfileService,
) -> None:
    try:
        height = float(message.text.replace(",", "."))  # type: ignore[union-attr]
        assert 50 <= height <= 250
    except (ValueError, AssertionError, TypeError):
        await message.answer("Введи корректный рост (например: 175):")
        return
    user_id = message.from_user.id  # type: ignore[union-attr]
    profile = await profile_service.get(user_id)
    if not profile:
        await state.clear()
        await message.answer("Профиль не найден. Нажми /start.")
        return
    profile.height = height
    await profile_service.update(profile)
    await state.clear()
    bmr = calc_bmr(profile.weight, profile.height, profile.age, profile.gender)
    await message.answer(
        f"✅ Рост изменён: {height} см\n"
        f"🎯 BMR: <b>{bmr:.0f}</b> ккал/день",
        reply_markup=MAIN_KEYBOARD,
        parse_mode="HTML",
    )


@router.message(EditProfileStates.waiting_age)
async def edit_age(
    message: types.Message, state: FSMContext, profile_service: ProfileService,
) -> None:
    try:
        age = int(message.text)  # type: ignore[union-attr]
        assert 5 <= age <= 120
    except (ValueError, AssertionError, TypeError):
        await message.answer("Введи корректный возраст (например: 25):")
        return
    user_id = message.from_user.id  # type: ignore[union-attr]
    profile = await profile_service.get(user_id)
    if not profile:
        await state.clear()
        await message.answer("Профиль не найден. Нажми /start.")
        return
    profile.age = age
    await profile_service.update(profile)
    await state.clear()
    bmr = calc_bmr(profile.weight, profile.height, profile.age, profile.gender)
    await message.answer(
        f"✅ Возраст изменён: {age}\n"
        f"🎯 BMR: <b>{bmr:.0f}</b> ккал/день",
        reply_markup=MAIN_KEYBOARD,
        parse_mode="HTML",
    )
