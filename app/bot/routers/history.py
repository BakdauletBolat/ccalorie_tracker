import logging
from datetime import date

from aiogram import F, Router, types
from aiogram.filters import Command

from app.bot import texts
from app.bot.keyboards import day_entries_keyboard, entry_view_keyboard, workout_view_keyboard
from app.services import FoodService, ProfileService, StatsService, WorkoutService
from app.services import time_service

logger = logging.getLogger(__name__)

router = Router(name="history")


async def show_day(
    message: types.Message,
    user_id: int,
    stats_service: StatsService,
    profile_service: ProfileService,
    day: date | None = None,
) -> None:
    profile = await profile_service.get(user_id)
    today = time_service.today(profile.timezone if profile else None)
    day = day or today
    logger.info("user=%s запросил историю за %s", user_id, day)

    summary = await stats_service.day_summary(user_id, day)
    if not summary.entries and not summary.workouts:
        await message.answer(f"Записей за {day.strftime('%d.%m.%Y')} нет.")
        return

    await message.answer(
        texts.day_summary_text(summary, today),
        reply_markup=day_entries_keyboard(summary.entries, summary.workouts, day),
        parse_mode="HTML",
    )


async def _refresh_day(
    message: types.Message,
    user_id: int,
    day: date,
    stats_service: StatsService,
    profile_service: ProfileService,
) -> None:
    """Перерисовывает сводку дня в существующем сообщении (после удаления/назад)."""
    profile = await profile_service.get(user_id)
    today = time_service.today(profile.timezone if profile else None)

    summary = await stats_service.day_summary(user_id, day)
    if not summary.entries and not summary.workouts:
        await message.edit_text(f"Записей за {texts.day_label(day, today)} нет.")
        return

    await message.edit_text(
        texts.day_summary_text(summary, today),
        reply_markup=day_entries_keyboard(summary.entries, summary.workouts, day),
        parse_mode="HTML",
    )


@router.message(Command("history"))
async def cmd_history(
    message: types.Message, stats_service: StatsService, profile_service: ProfileService,
) -> None:
    await show_day(message, message.from_user.id, stats_service, profile_service)  # type: ignore[union-attr]


@router.message(F.text == "🍽 Приёмы пищи")
async def btn_today(
    message: types.Message, stats_service: StatsService, profile_service: ProfileService,
) -> None:
    await show_day(message, message.from_user.id, stats_service, profile_service)  # type: ignore[union-attr]


@router.message(Command("clear"))
async def cmd_clear(
    message: types.Message, food_service: FoodService, profile_service: ProfileService,
) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    logger.info("user=%s вызвал очистку", user_id)
    profile = await profile_service.get(user_id)
    today = time_service.today(profile.timezone if profile else None)
    deleted = await food_service.clear_day(user_id, today)
    if deleted:
        await message.answer(f"Удалено {deleted} записей за сегодня.")
    else:
        await message.answer("Сегодня записей нет.")


@router.callback_query(F.data.startswith("view:"))
async def cb_view(callback: types.CallbackQuery, food_service: FoodService) -> None:
    # format: view:<entry_id>:<date>
    parts = callback.data.split(":", 2)  # type: ignore[union-attr]
    entry_id = parts[1]
    day = date.fromisoformat(parts[2])
    entry = await food_service.find_entry(callback.from_user.id, day, entry_id)
    if not entry:
        await callback.answer("Запись не найдена")
        return

    await callback.message.edit_text(  # type: ignore[union-attr]
        texts.entry_view_text(entry),
        reply_markup=entry_view_keyboard(entry_id, day),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("del:"))
async def cb_delete(
    callback: types.CallbackQuery,
    food_service: FoodService,
    stats_service: StatsService,
    profile_service: ProfileService,
) -> None:
    # format: del:<entry_id>:<date>
    parts = callback.data.split(":", 2)  # type: ignore[union-attr]
    entry_id = parts[1]
    day = date.fromisoformat(parts[2])
    deleted = await food_service.delete_entry(entry_id, callback.from_user.id)
    if not deleted:
        await callback.answer("Запись не найдена")
        return

    await callback.answer("Запись удалена")
    await _refresh_day(callback.message, callback.from_user.id, day, stats_service, profile_service)  # type: ignore[arg-type]


@router.callback_query(F.data.startswith("wview:"))
async def cb_workout_view(callback: types.CallbackQuery, stats_service: StatsService) -> None:
    # format: wview:<workout_id>:<date>
    parts = callback.data.split(":", 2)  # type: ignore[union-attr]
    workout_id = parts[1]
    day = date.fromisoformat(parts[2])
    summary = await stats_service.day_summary(callback.from_user.id, day)
    workout = next((w for wid, w in summary.workouts if wid == workout_id), None)
    if not workout:
        await callback.answer("Тренировка не найдена")
        return

    await callback.message.edit_text(  # type: ignore[union-attr]
        texts.workout_view_text(workout),
        reply_markup=workout_view_keyboard(workout_id, day),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("wdel:"))
async def cb_workout_delete(
    callback: types.CallbackQuery,
    workout_service: WorkoutService,
    stats_service: StatsService,
    profile_service: ProfileService,
) -> None:
    # format: wdel:<workout_id>:<date>
    parts = callback.data.split(":", 2)  # type: ignore[union-attr]
    workout_id = parts[1]
    day = date.fromisoformat(parts[2])
    deleted = await workout_service.delete(workout_id, callback.from_user.id)
    if not deleted:
        await callback.answer("Тренировка не найдена")
        return

    await callback.answer("Тренировка удалена")
    await _refresh_day(callback.message, callback.from_user.id, day, stats_service, profile_service)  # type: ignore[arg-type]


@router.callback_query(F.data.startswith("back:"))
async def cb_back(
    callback: types.CallbackQuery,
    stats_service: StatsService,
    profile_service: ProfileService,
) -> None:
    day = date.fromisoformat(callback.data.split(":", 1)[1])  # type: ignore[union-attr]
    await _refresh_day(callback.message, callback.from_user.id, day, stats_service, profile_service)  # type: ignore[arg-type]
    await callback.answer()
