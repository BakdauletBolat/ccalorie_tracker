from datetime import date, timedelta

from aiogram import types

from app.bot.texts import product_title
from app.models import FavoriteDish, FoodEntry, ProductItem, WorkoutEntry
from app.services.nutrition import ACTIVITY_LABELS, GOAL_LABELS
from app.services.time_service import TIMEZONE_CHOICES

MAIN_KEYBOARD = types.ReplyKeyboardMarkup(
    keyboard=[
        [
            types.KeyboardButton(text="🍽 Приёмы пищи"),
            types.KeyboardButton(text="📊 Неделя"),
        ],
        [
            types.KeyboardButton(text="⭐ Избранное"),
            types.KeyboardButton(text="👤 Профиль"),
        ],
    ],
    resize_keyboard=True,
)


def gender_keyboard(callback_prefix: str) -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="👨 Мужской", callback_data=f"{callback_prefix}:male"),
            types.InlineKeyboardButton(text="👩 Женский", callback_data=f"{callback_prefix}:female"),
        ]
    ])


def profile_edit_keyboard() -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⚖️ Изменить вес", callback_data="edit:weight")],
        [types.InlineKeyboardButton(text="📏 Изменить рост", callback_data="edit:height")],
        [types.InlineKeyboardButton(text="🎂 Изменить возраст", callback_data="edit:age")],
        [types.InlineKeyboardButton(text="🚻 Изменить пол", callback_data="edit:gender")],
        [types.InlineKeyboardButton(text="🏃 Активность", callback_data="edit:activity")],
        [types.InlineKeyboardButton(text="🎯 Цель", callback_data="edit:goal")],
        [types.InlineKeyboardButton(text="🌍 Часовой пояс", callback_data="edit:timezone")],
    ])


def activity_keyboard(callback_prefix: str) -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=label, callback_data=f"{callback_prefix}:{key}")]
        for key, label in ACTIVITY_LABELS.items()
    ])


def goal_keyboard(callback_prefix: str) -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=label, callback_data=f"{callback_prefix}:{key}")]
        for key, label in GOAL_LABELS.items()
    ])


def timezone_keyboard() -> types.InlineKeyboardMarkup:
    buttons: list[list[types.InlineKeyboardButton]] = []
    row: list[types.InlineKeyboardButton] = []
    for iana, label in TIMEZONE_CHOICES:
        row.append(types.InlineKeyboardButton(text=label, callback_data=f"settz:{iana}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)


def day_entries_keyboard(
    entries: list[tuple[str, FoodEntry]],
    workouts: list[tuple[str, WorkoutEntry]],
    day: date,
) -> types.InlineKeyboardMarkup:
    day_str = day.isoformat()
    buttons = [
        [
            types.InlineKeyboardButton(
                text=f"{i}. {e.description} — {e.nutrition.calories:.0f} ккал",
                callback_data=f"view:{entry_id}:{day_str}",
            )
        ]
        for i, (entry_id, e) in enumerate(entries, 1)
    ]
    buttons.extend(
        [
            types.InlineKeyboardButton(
                text=f"🏋️ {w.description} — {w.calories:.0f} ккал",
                callback_data=f"wview:{workout_id}:{day_str}",
            )
        ]
        for workout_id, w in workouts
    )
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)


def entry_view_keyboard(entry_id: str, day: date) -> types.InlineKeyboardMarkup:
    day_str = day.isoformat()
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⭐ В избранное", callback_data=f"favadd:{entry_id}")],
        [types.InlineKeyboardButton(text="❌ Удалить", callback_data=f"del:{entry_id}:{day_str}")],
        [types.InlineKeyboardButton(text="◀️ Назад", callback_data=f"back:{day_str}")],
    ])


def workout_view_keyboard(workout_id: str, day: date) -> types.InlineKeyboardMarkup:
    day_str = day.isoformat()
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="❌ Удалить", callback_data=f"wdel:{workout_id}:{day_str}")],
        [types.InlineKeyboardButton(text="◀️ Назад", callback_data=f"back:{day_str}")],
    ])


def confirmed_keyboard(entry_id: str) -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⭐ В избранное", callback_data=f"favadd:{entry_id}")],
    ])


def favorites_list_keyboard(favorites: list[tuple[str, FavoriteDish]]) -> types.InlineKeyboardMarkup:
    buttons = [
        [
            types.InlineKeyboardButton(
                text=f"{dish.name} — {dish.nutrition.calories:.0f} ккал",
                callback_data=f"fav:{fav_id}",
            )
        ]
        for fav_id, dish in favorites
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)


def favorite_view_keyboard(fav_id: str) -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Записать на сегодня", callback_data=f"favrec:{fav_id}")],
        [types.InlineKeyboardButton(text="🗑 Удалить из избранного", callback_data=f"favdel:{fav_id}")],
        [types.InlineKeyboardButton(text="◀️ К списку", callback_data="favlist")],
    ])


def week_nav_keyboard(start: date) -> types.InlineKeyboardMarkup:
    prev_week = (start - timedelta(days=7)).isoformat()
    next_week = (start + timedelta(days=7)).isoformat()
    return types.InlineKeyboardMarkup(inline_keyboard=[[
        types.InlineKeyboardButton(text="◀️ Назад", callback_data=f"week:{prev_week}"),
        types.InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"week:{next_week}"),
    ]])


BARCODE_GRAM_CHOICES = [30, 50, 100, 150, 200, 250, 330, 500]


def barcode_grams_keyboard(barcode: str) -> types.InlineKeyboardMarkup:
    buttons: list[list[types.InlineKeyboardButton]] = []
    row: list[types.InlineKeyboardButton] = []
    for grams in BARCODE_GRAM_CHOICES:
        row.append(types.InlineKeyboardButton(text=f"{grams} г", callback_data=f"bcg:{barcode}:{grams}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)


def pending_keyboard(items: list[ProductItem]) -> types.InlineKeyboardMarkup:
    buttons: list[list[types.InlineKeyboardButton]] = [
        [
            types.InlineKeyboardButton(
                text=f"❌ {i + 1}. {product_title(item)}",
                callback_data=f"pdel:{i}",
            )
        ]
        for i, item in enumerate(items)
    ]
    buttons.append([
        types.InlineKeyboardButton(text="✅ Записать", callback_data="confirm"),
        types.InlineKeyboardButton(text="🚫 Отмена", callback_data="cancel"),
    ])
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)
