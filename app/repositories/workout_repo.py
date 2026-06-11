import logging
from datetime import date

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models import WorkoutEntry
from app.repositories.base import day_bounds

logger = logging.getLogger(__name__)


class WorkoutRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:  # type: ignore[type-arg]
        self._col = db.workouts

    async def save(self, entry: WorkoutEntry) -> str:
        result = await self._col.insert_one(entry.model_dump())
        entry_id = str(result.inserted_id)
        logger.info(
            "Тренировка id=%s user=%s: %s %.0f ккал",
            entry_id, entry.user_id, entry.description, entry.calories,
        )
        return entry_id

    async def get_for_day(self, user_id: int, day: date) -> list[tuple[str, WorkoutEntry]]:
        start, end = day_bounds(day)
        cursor = self._col.find({
            "user_id": user_id,
            "created_at": {"$gte": start, "$lte": end},
        }).sort("created_at", 1)
        return [(str(doc["_id"]), WorkoutEntry(**doc)) async for doc in cursor]

    async def get_range(self, user_id: int, start_day: date, end_day: date) -> list[tuple[str, WorkoutEntry]]:
        start, _ = day_bounds(start_day)
        _, end = day_bounds(end_day)
        cursor = self._col.find({
            "user_id": user_id,
            "created_at": {"$gte": start, "$lte": end},
        }).sort("created_at", 1)
        return [(str(doc["_id"]), WorkoutEntry(**doc)) async for doc in cursor]

    async def delete(self, entry_id: str, user_id: int) -> bool:
        result = await self._col.delete_one({
            "_id": ObjectId(entry_id),
            "user_id": user_id,
        })
        return result.deleted_count > 0
