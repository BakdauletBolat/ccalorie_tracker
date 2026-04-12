import logging
from datetime import date, datetime, time

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from bson import ObjectId

from app.config import settings
from app.models import DailyProfileSnapshot, FoodEntry, UserProfile

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


# ── Profile ──────────────────────────────────────────────


async def upsert_user_profile(profile: UserProfile) -> None:
    db = get_db()
    await db.users.update_one(
        {"user_id": profile.user_id},
        {"$set": profile.model_dump()},
        upsert=True,
    )
    logger.info("Профиль сохранён для user=%s", profile.user_id)


async def get_user_profile(user_id: int) -> UserProfile | None:
    db = get_db()
    doc = await db.users.find_one({"user_id": user_id})
    if not doc:
        return None
    return UserProfile(**doc)


async def upsert_daily_snapshot(snapshot: DailyProfileSnapshot) -> None:
    db = get_db()
    await db.daily_profiles.update_one(
        {"user_id": snapshot.user_id, "date": snapshot.date.isoformat()},
        {"$set": {**snapshot.model_dump(), "date": snapshot.date.isoformat()}},
        upsert=True,
    )
    logger.info("Снимок сохранён для user=%s за %s", snapshot.user_id, snapshot.date)


async def get_daily_snapshot(user_id: int, day: date) -> DailyProfileSnapshot | None:
    db = get_db()
    doc = await db.daily_profiles.find_one(
        {"user_id": user_id, "date": day.isoformat()},
    )
    if not doc:
        return None
    doc["date"] = date.fromisoformat(doc["date"])
    return DailyProfileSnapshot(**doc)


async def get_user_active_days(user_id: int) -> list[date]:
    db = get_db()
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}}}},
        {"$sort": {"_id": 1}},
    ]
    days: list[date] = []
    async for doc in db.food_entries.aggregate(pipeline):
        days.append(date.fromisoformat(doc["_id"]))
    return days


async def bulk_create_daily_snapshots(snapshots: list[DailyProfileSnapshot]) -> int:
    if not snapshots:
        return 0
    db = get_db()
    ops = []
    from pymongo import UpdateOne
    for s in snapshots:
        ops.append(UpdateOne(
            {"user_id": s.user_id, "date": s.date.isoformat()},
            {"$set": {**s.model_dump(), "date": s.date.isoformat()}},
            upsert=True,
        ))
    result = await db.daily_profiles.bulk_write(ops)
    count = result.upserted_count + result.modified_count
    logger.info("Bulk создано/обновлено %d снимков для user=%s", count, snapshots[0].user_id)
    return count
