from datetime import datetime

from pydantic import BaseModel

from app.models.food import NutritionData, ProductItem


class FavoriteDish(BaseModel):
    user_id: int
    name: str
    items: list[ProductItem]
    nutrition: NutritionData
    created_at: datetime
