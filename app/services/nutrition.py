from app.models import NutritionData, ProductItem

# Коэффициенты активности (множитель к BMR)
ACTIVITY_FACTORS: dict[str, float] = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}

ACTIVITY_LABELS: dict[str, str] = {
    "sedentary": "🪑 Сидячий образ жизни",
    "light": "🚶 Лёгкая (1–3 тренировки/нед)",
    "moderate": "🏃 Средняя (3–5 тренировок/нед)",
    "active": "💪 Высокая (6–7 тренировок/нед)",
    "very_active": "🔥 Очень высокая (физ. работа)",
}

# Корректировка нормы калорий под цель
GOAL_FACTORS: dict[str, float] = {
    "lose": 0.85,
    "maintain": 1.0,
    "gain": 1.10,
}

GOAL_LABELS: dict[str, str] = {
    "lose": "📉 Похудеть",
    "maintain": "⚖️ Поддерживать вес",
    "gain": "📈 Набрать массу",
}


def calc_bmr(weight: float, height: float, age: int, gender: str) -> float:
    """Формула Миффлина-Сан Жеора (2005)."""
    base = 10 * weight + 6.25 * height - 5 * age
    if gender == "male":
        return base + 5
    return base - 161


def calc_tdee(bmr: float, activity_level: str) -> float:
    return bmr * ACTIVITY_FACTORS[activity_level]


def calc_target_calories(
    bmr: float, activity_level: str | None, goal: str | None,
) -> float | None:
    """Дневная норма: BMR × активность × цель. None, если активность или цель не указаны."""
    if activity_level not in ACTIVITY_FACTORS or goal not in GOAL_FACTORS:
        return None
    return calc_tdee(bmr, activity_level) * GOAL_FACTORS[goal]


def sum_nutrition(items: list[ProductItem]) -> NutritionData:
    total = NutritionData(calories=0, protein=0, fat=0, carbs=0)
    for item in items:
        total.calories += item.nutrition.calories
        total.protein += item.nutrition.protein
        total.fat += item.nutrition.fat
        total.carbs += item.nutrition.carbs
    return total


def add_nutrition(total: NutritionData, n: NutritionData) -> None:
    total.calories += n.calories
    total.protein += n.protein
    total.fat += n.fat
    total.carbs += n.carbs
