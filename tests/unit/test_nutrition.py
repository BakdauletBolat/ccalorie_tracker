from app.models import NutritionData, ProductItem
from app.services.nutrition import calc_bmr, calc_target_calories, calc_tdee, sum_nutrition


def _product(calories: float, protein: float = 0, fat: float = 0, carbs: float = 0) -> ProductItem:
    return ProductItem(
        description="тест",
        short_description="тест",
        nutrition=NutritionData(calories=calories, protein=protein, fat=fat, carbs=carbs),
    )


def test_bmr_male():
    # Миффлин-Сан Жеор: 10*80 + 6.25*180 - 5*30 + 5 = 1780
    assert calc_bmr(80, 180, 30, "male") == 1780


def test_bmr_female():
    # 10*60 + 6.25*165 - 5*25 - 161 = 1345.25
    assert calc_bmr(60, 165, 25, "female") == 1345.25


def test_tdee():
    assert calc_tdee(1780, "sedentary") == 1780 * 1.2
    assert calc_tdee(1780, "moderate") == 1780 * 1.55


def test_target_calories_lose():
    # 1780 * 1.55 * 0.85 = 2345.15
    assert calc_target_calories(1780, "moderate", "lose") == 1780 * 1.55 * 0.85


def test_target_calories_maintain():
    assert calc_target_calories(1780, "sedentary", "maintain") == 1780 * 1.2


def test_target_calories_gain():
    assert calc_target_calories(1780, "active", "gain") == 1780 * 1.725 * 1.10


def test_target_calories_missing_activity_or_goal():
    assert calc_target_calories(1780, None, "lose") is None
    assert calc_target_calories(1780, "moderate", None) is None
    assert calc_target_calories(1780, "unknown", "lose") is None


def test_sum_nutrition_empty():
    total = sum_nutrition([])
    assert total.calories == 0
    assert total.protein == 0


def test_sum_nutrition():
    total = sum_nutrition([
        _product(100, protein=10, fat=5, carbs=20),
        _product(250, protein=15, fat=10, carbs=30),
    ])
    assert total.calories == 350
    assert total.protein == 25
    assert total.fat == 15
    assert total.carbs == 50
