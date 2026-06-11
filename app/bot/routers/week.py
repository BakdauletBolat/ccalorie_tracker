import logging
from datetime import date

from aiogram import F, Router, types
from aiogram.filters import Command

from app.bot import texts
from app.bot.keyboards import week_nav_keyboard
from app.services import ProfileService, StatsService
from app.services import time_service

logger = logging.getLogger(__name__)

router = Router(name="week")


@router.message(Command("week"))
@router.message(F.text == "📊 Неделя")
async def btn_week(
    message: types.Message, stats_service: StatsService, profile_service: ProfileService,
) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    profile = await profile_service.get(user_id)
    today = time_service.today(profile.timezone if profile else None)

    summary = await stats_service.week_summary(user_id, today)
    await message.answer(
        texts.week_text(summary, today),
        reply_markup=week_nav_keyboard(summary.start),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("week:"))
async def cb_week(
    callback: types.CallbackQuery, stats_service: StatsService, profile_service: ProfileService,
) -> None:
    ref = date.fromisoformat(callback.data.split(":", 1)[1])  # type: ignore[union-attr]
    user_id = callback.from_user.id
    profile = await profile_service.get(user_id)
    today = time_service.today(profile.timezone if profile else None)

    summary = await stats_service.week_summary(user_id, ref)
    await callback.message.edit_text(  # type: ignore[union-attr]
        texts.week_text(summary, today),
        reply_markup=week_nav_keyboard(summary.start),
        parse_mode="HTML",
    )
    await callback.answer()
