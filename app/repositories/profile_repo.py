import logging
from datetime import date

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import UpdateOne

from app.models import DailyProfileSnapshot, UserProfile

logger = logging.getLogger(__name__)


class ProfileRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:  # type: ignore[type-arg]
        self._users = db.users
        self._snapshots = db.daily_profiles

    async def upsert_profile(self, profile: UserProfile) -> None:
        await self._users.update_one(
            {"user_id": profile.user_id},
            {"$set": profile.model_dump()},
            upsert=True,
        )
        logger.info("Профиль сохранён для user=%s", profile.user_id)

    async def get_profile(self, user_id: int) -> UserProfile | None:
        doc = await self._users.find_one({"user_id": user_id})
        if not doc:
            return None
        return UserProfile(**doc)

    async def upsert_snapshot(self, snapshot: DailyProfileSnapshot) -> None:
        await self._snapshots.update_one(
            {"user_id": snapshot.user_id, "date": snapshot.date.isoformat()},
            {"$set": {**snapshot.model_dump(), "date": snapshot.date.isoformat()}},
            upsert=True,
        )
        logger.info("Снимок сохранён для user=%s за %s", snapshot.user_id, snapshot.date)

    async def get_snapshot(self, user_id: int, day: date) -> DailyProfileSnapshot | None:
        doc = await self._snapshots.find_one({"user_id": user_id, "date": day.isoformat()})
        if not doc:
            return None
        doc["date"] = date.fromisoformat(doc["date"])
        return DailyProfileSnapshot(**doc)

    async def bulk_upsert_snapshots(self, snapshots: list[DailyProfileSnapshot]) -> int:
        if not snapshots:
            return 0
        ops = [
            UpdateOne(
                {"user_id": s.user_id, "date": s.date.isoformat()},
                {"$set": {**s.model_dump(), "date": s.date.isoformat()}},
                upsert=True,
            )
            for s in snapshots
        ]
        result = await self._snapshots.bulk_write(ops)
        count = result.upserted_count + result.modified_count
        logger.info("Bulk создано/обновлено %d снимков для user=%s", count, snapshots[0].user_id)
        return count
