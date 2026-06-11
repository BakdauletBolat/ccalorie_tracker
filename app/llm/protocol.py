from datetime import date
from typing import Protocol

from pydantic import BaseModel, Field


class ParserError(Exception):
    """LLM недоступен или вернул ошибку — пользователю предлагаем повторить позже."""


class ParsedProduct(BaseModel):
    description: str
    short_description: str
    grams: float | None = None
    calories: float
    protein: float
    fat: float
    carbs: float


class ParsedFoodList(BaseModel):
    products: list[ParsedProduct] = Field(default_factory=list)
    date: str | None = None  # YYYY-MM-DD, None = сегодня


class ParsedWorkoutData(BaseModel):
    description: str
    calories: float


class ParsedMessage(BaseModel):
    """Результат разбора сообщения: намерение + данные одним LLM-вызовом."""

    intent: str  # "food", "history", "workout", "other"
    products: list[ParsedProduct] = Field(default_factory=list)  # для intent="food"
    workout: ParsedWorkoutData | None = None  # для intent="workout"
    date: str | None = None  # YYYY-MM-DD, None = сегодня


class FoodParser(Protocol):
    async def parse_message(self, text: str, today: date) -> ParsedMessage: ...

    async def parse_food(self, text: str, today: date) -> ParsedFoodList: ...

    async def parse_food_photo(
        self, image: bytes, caption: str | None, today: date,
    ) -> ParsedFoodList: ...

    async def off_topic_reply(self, text: str) -> str: ...
