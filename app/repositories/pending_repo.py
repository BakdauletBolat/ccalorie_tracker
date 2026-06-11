import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models import PendingMeal

logger = logging.getLogger(__name__)


class PendingRepository:
    """Неподтверждённые приёмы пищи. Хранятся в Mongo, переживают рестарт бота."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:  # type: ignore[type-arg]
        self._col = db.pending_meals

    async def get(self, user_id: int) -> PendingMeal | None:
        doc = await self._col.find_one({"user_id": user_id})
        if not doc:
            return None
        return PendingMeal(**doc)

    async def set(self, meal: PendingMeal) -> None:
        await self._col.update_one(
            {"user_id": meal.user_id},
            {"$set": meal.model_dump(mode="json")},
            upsert=True,
        )

    async def clear(self, user_id: int) -> None:
        await self._col.delete_one({"user_id": user_id})
