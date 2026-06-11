from datetime import date, datetime

from pydantic import BaseModel, Field


class NutritionData(BaseModel):
    calories: float
    protein: float
    fat: float
    carbs: float


class ProductItem(BaseModel):
    description: str           # "Хлеб белый 45 г"
    short_description: str     # "Хлеб"
    grams: float | None = None
    nutrition: NutritionData


class FoodEntry(BaseModel):
    user_id: int
    description: str
    short_description: str = ""
    items: list[ProductItem] = Field(default_factory=list)
    nutrition: NutritionData
    created_at: datetime


class PendingMeal(BaseModel):
    """Продукты, ожидающие подтверждения пользователем."""

    user_id: int
    items: list[ProductItem] = Field(default_factory=list)
    entry_date: date | None = None  # None = сегодня
