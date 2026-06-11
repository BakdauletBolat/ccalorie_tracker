import logging

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models import FavoriteDish

logger = logging.getLogger(__name__)


class FavoriteRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:  # type: ignore[type-arg]
        self._col = db.favorites

    async def upsert(self, dish: FavoriteDish) -> str:
        """Сохраняет блюдо; одноимённое блюдо пользователя перезаписывается."""
        result = await self._col.update_one(
            {"user_id": dish.user_id, "name": dish.name},
            {"$set": dish.model_dump()},
            upsert=True,
        )
        if result.upserted_id is not None:
            fav_id = str(result.upserted_id)
        else:
            doc = await self._col.find_one({"user_id": dish.user_id, "name": dish.name})
            fav_id = str(doc["_id"])  # type: ignore[index]
        logger.info("Избранное id=%s user=%s: %s", fav_id, dish.user_id, dish.name)
        return fav_id

    async def list(self, user_id: int) -> list[tuple[str, FavoriteDish]]:
        cursor = self._col.find({"user_id": user_id}).sort("created_at", -1)
        return [(str(doc["_id"]), FavoriteDish(**doc)) async for doc in cursor]

    async def get(self, fav_id: str, user_id: int) -> FavoriteDish | None:
        doc = await self._col.find_one({"_id": ObjectId(fav_id), "user_id": user_id})
        if not doc:
            return None
        return FavoriteDish(**doc)

    async def delete(self, fav_id: str, user_id: int) -> bool:
        result = await self._col.delete_one({"_id": ObjectId(fav_id), "user_id": user_id})
        logger.info("Удаление избранного id=%s user=%s: %s", fav_id, user_id, result.deleted_count > 0)
        return result.deleted_count > 0
