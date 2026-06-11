import logging
from datetime import date

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models import FoodEntry
from app.repositories.base import day_bounds

logger = logging.getLogger(__name__)


class FoodRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:  # type: ignore[type-arg]
        self._col = db.food_entries

    async def save(self, entry: FoodEntry) -> str:
        result = await self._col.insert_one(entry.model_dump())
        entry_id = str(result.inserted_id)
        logger.info("Сохранена запись id=%s user=%s: %s", entry_id, entry.user_id, entry.description)
        return entry_id

    async def get_for_day(self, user_id: int, day: date) -> list[tuple[str, FoodEntry]]:
        start, end = day_bounds(day)
        cursor = self._col.find({
            "user_id": user_id,
            "created_at": {"$gte": start, "$lte": end},
        }).sort("created_at", 1)
        entries = [(str(doc["_id"]), FoodEntry(**doc)) async for doc in cursor]
        logger.info("Загружено %d записей для user=%s за %s", len(entries), user_id, day)
        return entries

    async def get_range(self, user_id: int, start_day: date, end_day: date) -> list[tuple[str, FoodEntry]]:
        start, _ = day_bounds(start_day)
        _, end = day_bounds(end_day)
        cursor = self._col.find({
            "user_id": user_id,
            "created_at": {"$gte": start, "$lte": end},
        }).sort("created_at", 1)
        entries = [(str(doc["_id"]), FoodEntry(**doc)) async for doc in cursor]
        logger.info("Загружено %d записей для user=%s за %s..%s", len(entries), user_id, start_day, end_day)
        return entries

    async def get_by_id(self, entry_id: str, user_id: int) -> FoodEntry | None:
        doc = await self._col.find_one({"_id": ObjectId(entry_id), "user_id": user_id})
        if not doc:
            return None
        return FoodEntry(**doc)

    async def delete(self, entry_id: str, user_id: int) -> bool:
        result = await self._col.delete_one({
            "_id": ObjectId(entry_id),
            "user_id": user_id,
        })
        logger.info("Удаление записи id=%s user=%s: %s", entry_id, user_id, result.deleted_count > 0)
        return result.deleted_count > 0

    async def clear_day(self, user_id: int, day: date) -> int:
        start, end = day_bounds(day)
        result = await self._col.delete_many({
            "user_id": user_id,
            "created_at": {"$gte": start, "$lte": end},
        })
        logger.info("Удалено %d записей для user=%s за %s", result.deleted_count, user_id, day)
        return int(result.deleted_count)

    async def active_days(self, user_id: int) -> list[date]:
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}}}},
            {"$sort": {"_id": 1}},
        ]
        return [date.fromisoformat(doc["_id"]) async for doc in self._col.aggregate(pipeline)]
