import logging
from datetime import date, datetime, time

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from bson import ObjectId

from app.config import settings
from app.models import FoodEntry

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None  # type: ignore[type-arg]
_db: AsyncIOMotorDatabase | None = None  # type: ignore[type-arg]


def get_db() -> AsyncIOMotorDatabase:  # type: ignore[type-arg]
    assert _db is not None
    return _db


def connect() -> None:
    global _client, _db
    _client = AsyncIOMotorClient(settings.MONGO_URI)
    _db = _client[settings.MONGO_DB_NAME]


def disconnect() -> None:
    global _client, _db
    if _client:
        _client.close()
    _client = None
    _db = None


async def save_entry(entry: FoodEntry) -> str:
    db = get_db()
    result = await db.food_entries.insert_one(entry.model_dump())
    entry_id = str(result.inserted_id)
    logger.info("Сохранена запись id=%s user=%s: %s", entry_id, entry.user_id, entry.description)
    return entry_id


async def get_entries(user_id: int, day: date | None = None) -> list[tuple[str, FoodEntry]]:
    db = get_db()
    find_dict: dict = {
        "user_id": user_id,
    }
    if day:
        start = datetime.combine(day, time.min)
        end = datetime.combine(day, time.max)
        find_dict["created_at"] = {"$gte": start, "$lte": end}

    cursor = db.food_entries.find(find_dict)
    entries = [(str(doc["_id"]), FoodEntry(**doc)) async for doc in cursor]
    logger.info("Загружено %d записей для user=%s за %s", len(entries), user_id, day)
    return entries


async def delete_entry(entry_id: str, user_id: int) -> bool:
    db = get_db()
    result = await db.food_entries.delete_one({
        "_id": ObjectId(entry_id),
        "user_id": user_id,
    })
    logger.info("Удаление записи id=%s user=%s: %s", entry_id, user_id, result.deleted_count > 0)
    return result.deleted_count > 0


async def get_entries_range(
    user_id: int, start_day: date, end_day: date,
) -> list[tuple[str, FoodEntry]]:
    db = get_db()
    start = datetime.combine(start_day, time.min)
    end = datetime.combine(end_day, time.max)
    cursor = db.food_entries.find({
        "user_id": user_id,
        "created_at": {"$gte": start, "$lte": end},
    })
    entries = [(str(doc["_id"]), FoodEntry(**doc)) async for doc in cursor]
    logger.info("Загружено %d записей для user=%s за %s..%s", len(entries), user_id, start_day, end_day)
    return entries


async def clear_entries(user_id: int, day: date) -> int:
    db = get_db()
    start = datetime.combine(day, time.min)
    end = datetime.combine(day, time.max)
    result = await db.food_entries.delete_many({
        "user_id": user_id,
        "created_at": {"$gte": start, "$lte": end},
    })
    logger.info("Удалено %d записей для user=%s за %s", result.deleted_count, user_id, day)
    return int(result.deleted_count)
