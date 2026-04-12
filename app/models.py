from datetime import date, datetime

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


class UserProfile(BaseModel):
    user_id: int
    gender: str  # "male" / "female"
    weight: float  # кг
    height: float  # см
    age: int


class DailyProfileSnapshot(BaseModel):
    user_id: int
    weight: float
    height: float
    age: int
    date: date


class WorkoutEntry(BaseModel):
    user_id: int
    calories: float
    description: str
    created_at: datetime
