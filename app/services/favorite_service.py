import logging

from app.models import FavoriteDish, FoodEntry
from app.repositories import FavoriteRepository, FoodRepository
from app.services import time_service
from app.services.food_service import entry_from_items

logger = logging.getLogger(__name__)

MAX_NAME_LENGTH = 60


class FavoriteService:
    def __init__(self, favorites: FavoriteRepository, foods: FoodRepository) -> None:
        self._favorites = favorites
        self._foods = foods

    async def add_from_entry(self, entry: FoodEntry, tz_name: str | None) -> tuple[str, FavoriteDish]:
        name = (entry.short_description or entry.description)[:MAX_NAME_LENGTH]
        dish = FavoriteDish(
            user_id=entry.user_id,
            name=name,
            items=entry.items,
            nutrition=entry.nutrition,
            created_at=time_service.now(tz_name),
        )
        fav_id = await self._favorites.upsert(dish)
        return fav_id, dish

    async def list(self, user_id: int) -> list[tuple[str, FavoriteDish]]:
        return await self._favorites.list(user_id)

    async def get(self, fav_id: str, user_id: int) -> FavoriteDish | None:
        return await self._favorites.get(fav_id, user_id)

    async def delete(self, fav_id: str, user_id: int) -> bool:
        return await self._favorites.delete(fav_id, user_id)

    async def record(self, fav_id: str, user_id: int, tz_name: str | None) -> FoodEntry | None:
        """Записывает избранное блюдо как приём пищи на сегодня. Без LLM."""
        dish = await self._favorites.get(fav_id, user_id)
        if dish is None:
            return None
        entry = entry_from_items(user_id, dish.items, None, tz_name)
        await self._foods.save(entry)
        logger.info("user=%s записал избранное: %s", user_id, dish.name)
        return entry
