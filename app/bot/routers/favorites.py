import logging

from aiogram import F, Router, types
from aiogram.filters import Command

from app.bot import texts
from app.bot.keyboards import favorite_view_keyboard, favorites_list_keyboard
from app.services import FavoriteService, FoodService, ProfileService
from app.services import time_service

logger = logging.getLogger(__name__)

router = Router(name="favorites")


@router.message(Command("favorites"))
@router.message(F.text == "⭐ Избранное")
async def btn_favorites(message: types.Message, favorite_service: FavoriteService) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    favorites = await favorite_service.list(user_id)
    await message.answer(
        texts.favorites_list_text(len(favorites)),
        reply_markup=favorites_list_keyboard(favorites) if favorites else None,
        parse_mode="HTML",
    )


@router.callback_query(F.data == "favlist")
async def cb_favorites_list(callback: types.CallbackQuery, favorite_service: FavoriteService) -> None:
    favorites = await favorite_service.list(callback.from_user.id)
    await callback.message.edit_text(  # type: ignore[union-attr]
        texts.favorites_list_text(len(favorites)),
        reply_markup=favorites_list_keyboard(favorites) if favorites else None,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("favadd:"))
async def cb_favorite_add(
    callback: types.CallbackQuery,
    favorite_service: FavoriteService,
    food_service: FoodService,
    profile_service: ProfileService,
) -> None:
    entry_id = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    user_id = callback.from_user.id
    entry = await food_service.get_entry_by_id(entry_id, user_id)
    if entry is None:
        await callback.answer("Запись не найдена")
        return

    profile = await profile_service.get(user_id)
    _, dish = await favorite_service.add_from_entry(entry, profile.timezone if profile else None)
    await callback.answer(f"⭐ Сохранено: {dish.name}")
    await callback.message.answer(  # type: ignore[union-attr]
        f"⭐ <b>{dish.name}</b> в избранном!\n"
        "Теперь можно записать его в один тап: кнопка «⭐ Избранное».",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("fav:"))
async def cb_favorite_view(callback: types.CallbackQuery, favorite_service: FavoriteService) -> None:
    fav_id = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    dish = await favorite_service.get(fav_id, callback.from_user.id)
    if dish is None:
        await callback.answer("Блюдо не найдено")
        return

    await callback.message.edit_text(  # type: ignore[union-attr]
        texts.favorite_view_text(dish),
        reply_markup=favorite_view_keyboard(fav_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("favrec:"))
async def cb_favorite_record(
    callback: types.CallbackQuery,
    favorite_service: FavoriteService,
    profile_service: ProfileService,
) -> None:
    fav_id = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    user_id = callback.from_user.id

    profile = await profile_service.ensure_today_snapshot(user_id)
    tz = profile.timezone if profile else None

    entry = await favorite_service.record(fav_id, user_id, tz)
    if entry is None:
        await callback.answer("Блюдо не найдено")
        return

    today = time_service.today(tz)
    await callback.message.edit_text(  # type: ignore[union-attr]
        texts.confirmed_text(entry, None, today),
        parse_mode="HTML",
    )
    await callback.answer("Записано!")


@router.callback_query(F.data.startswith("favdel:"))
async def cb_favorite_delete(callback: types.CallbackQuery, favorite_service: FavoriteService) -> None:
    fav_id = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    deleted = await favorite_service.delete(fav_id, callback.from_user.id)
    if not deleted:
        await callback.answer("Блюдо не найдено")
        return

    await callback.answer("Удалено из избранного")
    favorites = await favorite_service.list(callback.from_user.id)
    await callback.message.edit_text(  # type: ignore[union-attr]
        texts.favorites_list_text(len(favorites)),
        reply_markup=favorites_list_keyboard(favorites) if favorites else None,
        parse_mode="HTML",
    )
