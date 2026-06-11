"""Рендеринг сообщений бота. Чистые функции: данные → текст."""

from datetime import date

from app.models import (
    FavoriteDish,
    FoodEntry,
    NutritionData,
    ProductInfo,
    ProductItem,
    UserProfile,
    WorkoutEntry,
)
from app.services import DaySummary, WeekSummary
from app.services import time_service
from app.services.nutrition import (
    ACTIVITY_LABELS,
    GOAL_LABELS,
    calc_bmr,
    calc_target_calories,
    calc_tdee,
    sum_nutrition,
)

SERVICE_OVERLOADED = "Сервис перегружен, попробуйте через 30 секунд."

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def day_label(day: date, today: date) -> str:
    return "Сегодня" if day == today else day.strftime("%d.%m.%Y")


def product_title(item: ProductItem) -> str:
    title = item.short_description or item.description
    if item.grams is not None:
        return f"{title} ({item.grams:.0f}г)"
    return title


def _product_lines(items: list[ProductItem]) -> list[str]:
    return [
        f"{i}. {product_title(item)}\n"
        f"🔥 {item.nutrition.calories:.0f} ккал | "
        f"🥩 {item.nutrition.protein:.0f}Б | "
        f"🧈 {item.nutrition.fat:.0f}Ж | "
        f"🍞 {item.nutrition.carbs:.0f}У"
        for i, item in enumerate(items, 1)
    ]


def _totals_line(total: NutritionData) -> str:
    return (
        f"🔥 {total.calories:.0f} ккал | "
        f"🥩 {total.protein:.0f} Б | "
        f"🧈 {total.fat:.0f} Ж | "
        f"🍞 {total.carbs:.0f} У"
    )


def pending_text(items: list[ProductItem], entry_date: date | None, today: date) -> str:
    date_label = ""
    if entry_date and entry_date != today:
        date_label = f"\n📅 Дата: {entry_date.strftime('%d.%m.%Y')}\n"

    items_text = "\n\n".join(_product_lines(items))
    return (
        f"🍽 <b>Приём пищи</b>{date_label}\n\n"
        f"{items_text}\n\n"
        f"<b>Итого:</b>\n"
        f"{_totals_line(sum_nutrition(items))}\n\n"
        f"Добавь ещё продукт, измени список или подтверди:"
    )


def confirmed_text(entry: FoodEntry, entry_date: date | None, today: date) -> str:
    date_label = ""
    if entry_date and entry_date != today:
        date_label = f"\n📅 Дата: {entry_date.strftime('%d.%m.%Y')}"

    return (
        f"✅ <b>Записано!</b>{date_label}\n\n"
        f"{chr(10).join(_product_lines(entry.items))}\n\n"
        f"{_totals_line(entry.nutrition)}"
    )


def entry_view_text(entry: FoodEntry) -> str:
    if entry.items:
        lines = [f"🍽 <b>{entry.short_description or entry.description}</b>", ""]
        product_lines = _product_lines(entry.items)
        for i, line in enumerate(product_lines, 1):
            lines.append(line)
            if i < len(product_lines):
                lines.append("")
        lines.extend([
            "",
            "<b>Итого:</b>",
            f"🔥 {entry.nutrition.calories:.0f} ккал | "
            f"🥩 {entry.nutrition.protein:.0f} г | "
            f"🧈 {entry.nutrition.fat:.0f} г | "
            f"🍞 {entry.nutrition.carbs:.0f} г",
            "",
            f"🕐 {entry.created_at.strftime('%H:%M')}",
        ])
        return "\n".join(lines)

    return (
        f"🍽 <b>{entry.description}</b>\n\n"
        f"🔥 Калории: {entry.nutrition.calories:.0f} ккал\n"
        f"🥩 Белки: {entry.nutrition.protein:.0f} г\n"
        f"🧈 Жиры: {entry.nutrition.fat:.0f} г\n"
        f"🍞 Углеводы: {entry.nutrition.carbs:.0f} г\n\n"
        f"🕐 {entry.created_at.strftime('%H:%M')}"
    )


def day_summary_text(summary: DaySummary, today: date) -> str:
    text = (
        f"📅 <b>{day_label(summary.day, today)}</b>\n\n"
        f"🔥 Калории: <b>{summary.total.calories:.0f}</b> ккал\n"
        f"🥩 Белки: <b>{summary.total.protein:.0f}</b> г\n"
        f"🧈 Жиры: <b>{summary.total.fat:.0f}</b> г\n"
        f"🍞 Углеводы: <b>{summary.total.carbs:.0f}</b> г\n"
    )

    if summary.bmr is not None:
        if summary.target is not None:
            text += f"\n🎯 Норма: {summary.target:.0f} ккал"
        else:
            text += f"\n🎯 BMR: {summary.bmr:.0f} ккал"
        if summary.burned > 0:
            text += f"\n🏋️ Сожжено: {summary.burned:.0f} ккал"
        diff = summary.diff
        assert diff is not None
        if diff <= 0:
            text += f"\n📉 Осталось: <b>{abs(diff):.0f}</b> ккал"
        else:
            text += f"\n📈 Сверх нормы: <b>{diff:.0f}</b> ккал"
        if summary.target is None:
            text += "\n\n💡 Укажи активность и цель в 👤 Профиль — посчитаю точную норму"

    counts = f"Записей: {len(summary.entries)}"
    if summary.workouts:
        counts += f", тренировок: {len(summary.workouts)}"
    text += f"\n\n{counts} — нажми чтобы посмотреть подробнее:"
    return text


def barcode_grams_text(info: ProductInfo) -> str:
    return (
        f"📦 <b>{info.name}</b>\n\n"
        f"На 100 г: 🔥 {info.calories_100g:.0f} ккал | "
        f"🥩 {info.protein_100g:.0f}Б | "
        f"🧈 {info.fat_100g:.0f}Ж | "
        f"🍞 {info.carbs_100g:.0f}У\n\n"
        f"Выбери вес порции — запишу сразу:"
    )


def workout_view_text(workout: WorkoutEntry) -> str:
    return (
        f"🏋️ <b>{workout.description}</b>\n\n"
        f"🔥 Сожжено: <b>{workout.calories:.0f}</b> ккал\n\n"
        f"🕐 {workout.created_at.strftime('%H:%M')}"
    )


def favorites_list_text(count: int) -> str:
    if count == 0:
        return (
            "⭐ В избранном пока пусто.\n\n"
            "Запиши приём пищи и нажми «⭐ В избранное» — "
            "потом сможешь записывать его в один тап."
        )
    return f"⭐ <b>Избранные блюда</b> ({count})\n\nНажми, чтобы посмотреть и записать:"


def favorite_view_text(dish: FavoriteDish) -> str:
    items_text = "\n\n".join(_product_lines(dish.items))
    return (
        f"⭐ <b>{dish.name}</b>\n\n"
        f"{items_text}\n\n"
        f"<b>Итого:</b>\n"
        f"{_totals_line(dish.nutrition)}"
    )


def week_text(summary: WeekSummary, today: date) -> str:
    lines: list[str] = []
    for i, day_line in enumerate(summary.days):
        label = f"{WEEKDAYS[i]} {day_line.day.strftime('%d.%m')}"
        if day_line.day == today:
            label = f"<b>{label} (сегодня)</b>"
        n = day_line.nutrition
        if n:
            lines.append(
                f"{label} — {n.calories:.0f} ккал | "
                f"{n.protein:.0f}Б {n.fat:.0f}Ж {n.carbs:.0f}У"
            )
        else:
            lines.append(f"{label} — нет записей")

    text = (
        f"📊 <b>Неделя {summary.start.strftime('%d.%m')} – {summary.end.strftime('%d.%m.%Y')}</b>\n\n"
        + "\n".join(lines)
        + f"\n\n<b>Итого за неделю:</b>\n"
        f"🔥 {summary.total.calories:.0f} ккал | "
        f"🥩 {summary.total.protein:.0f} Б | "
        f"🧈 {summary.total.fat:.0f} Ж | "
        f"🍞 {summary.total.carbs:.0f} У"
    )

    if summary.total_burned > 0:
        text += f"\n🏋️ Сожжено: {summary.total_burned:.0f} ккал"

    if summary.days_with_bmr > 0:
        if summary.total_deficit <= 0:
            text += f"\n📉 Дефицит за неделю: <b>{abs(summary.total_deficit):.0f}</b> ккал"
        else:
            text += f"\n📈 Профицит за неделю: <b>{summary.total_deficit:.0f}</b> ккал"

    return text


def gender_label(gender: str) -> str:
    return "Мужской" if gender == "male" else "Женский"


def profile_text(profile: UserProfile) -> str:
    bmr = calc_bmr(profile.weight, profile.height, profile.age, profile.gender)
    activity = ACTIVITY_LABELS.get(profile.activity_level or "", "не указана")
    goal = GOAL_LABELS.get(profile.goal or "", "не указана")
    text = (
        f"👤 <b>Твой профиль</b>\n\n"
        f"🚻 Пол: {gender_label(profile.gender)}\n"
        f"⚖️ Вес: {profile.weight} кг\n"
        f"📏 Рост: {profile.height} см\n"
        f"🎂 Возраст: {profile.age}\n"
        f"🏃 Активность: {activity}\n"
        f"🎯 Цель: {goal}\n"
        f"🌍 Часовой пояс: {time_service.tz_label(profile.timezone)}\n\n"
        f"🔥 BMR: <b>{bmr:.0f}</b> ккал/день"
    )
    target = calc_target_calories(bmr, profile.activity_level, profile.goal)
    if target is not None:
        assert profile.activity_level is not None
        text += (
            f"\n⚡ TDEE: <b>{calc_tdee(bmr, profile.activity_level):.0f}</b> ккал/день"
            f"\n🎯 Норма: <b>{target:.0f}</b> ккал/день"
        )
    else:
        text += "\n\n💡 Укажи активность и цель — посчитаю твою дневную норму"
    return text


def target_line(profile: UserProfile) -> str:
    """Строка с нормой (или BMR, если активность/цель не указаны) для приветствий."""
    bmr = calc_bmr(profile.weight, profile.height, profile.age, profile.gender)
    target = calc_target_calories(bmr, profile.activity_level, profile.goal)
    if target is not None:
        return f"🎯 Твоя норма: <b>{target:.0f}</b> ккал/день"
    return f"🎯 Твой BMR: <b>{bmr:.0f}</b> ккал/день"


HELP = (
    "🍽 <b>CALorie Tracker — что я умею</b>\n\n"
    "<b>Записать еду</b> — просто напиши:\n"
    "• «Овсянка и банан»\n"
    "• «Гречка 150г и курица»\n"
    "• «Вчера ел плов 400г»\n"
    "• «Кофе с молоком, 50 ккал»\n\n"
    "<b>Фото и штрих-код:</b>\n"
    "• Фото еды — распознаю блюда и КБЖУ\n"
    "• Фото штрих-кода — точные КБЖУ с этикетки\n"
    "• Можно прислать код цифрами: «4870123456789»\n\n"
    "<b>Тренировки:</b>\n"
    "• «Пробежал 5 км»\n"
    "• «Сжёг 500 ккал на тренировке»\n\n"
    "<b>История:</b>\n"
    "• «Что я ел вчера», «покажи за 5 мая»\n"
    "• Кнопка 🍽 Приёмы пищи — сегодня\n"
    "• Кнопка 📊 Неделя — отчёт за неделю\n\n"
    "<b>Избранное:</b>\n"
    "• После записи нажми «⭐ В избранное»\n"
    "• Кнопка ⭐ Избранное — записать блюдо в один тап\n\n"
    "<b>Команды:</b>\n"
    "/help — это сообщение\n"
    "/history — записи за сегодня\n"
    "/week — отчёт за неделю\n"
    "/favorites — избранные блюда\n"
    "/clear — удалить все записи за сегодня\n\n"
    "⚙️ Вес, рост, активность, цель и часовой пояс — в 👤 Профиль"
)
