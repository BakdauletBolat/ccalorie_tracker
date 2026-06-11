import logging
from datetime import date, datetime, time

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None  # type: ignore[type-arg]


def connect() -> AsyncIOMotorDatabase:  # type: ignore[type-arg]
    global _client
    _client = AsyncIOMotorClient(settings.MONGO_URI)
    return _client[settings.MONGO_DB_NAME]


def disconnect() -> None:
    global _client
    if _client:
        _client.close()
    _client = None


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:  # type: ignore[type-arg]
    await db.food_entries.create_index([("user_id", 1), ("created_at", 1)])
    await db.workouts.create_index([("user_id", 1), ("created_at", 1)])
    await db.daily_profiles.create_index([("user_id", 1), ("date", 1)], unique=True)
    await db.users.create_index([("user_id", 1)], unique=True)
    await db.pending_meals.create_index([("user_id", 1)], unique=True)
    await db.favorites.create_index([("user_id", 1), ("name", 1)], unique=True)
    await db.products.create_index([("barcode", 1)], unique=True)
    logger.info("Индексы MongoDB проверены")


def day_bounds(day: date) -> tuple[datetime, datetime]:
    return datetime.combine(day, time.min), datetime.combine(day, time.max)
