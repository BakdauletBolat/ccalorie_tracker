from datetime import datetime

from pydantic import BaseModel


class NutritionData(BaseModel):
    calories: float
    protein: float
    fat: float
    carbs: float


class FoodEntry(BaseModel):
    user_id: int
    description: str
    nutrition: NutritionData
    created_at: datetime
