import logging
from datetime import date, datetime

from app.llm.protocol import ParsedProduct
from app.models import FoodEntry, NutritionData, PendingMeal, ProductItem
from app.repositories import FoodRepository, PendingRepository
from app.services import time_service
from app.services.nutrition import sum_nutrition

logger = logging.getLogger(__name__)


def product_from_parsed(parsed: ParsedProduct) -> ProductItem:
    return ProductItem(
        description=parsed.description,
        short_description=parsed.short_description,
        grams=parsed.grams,
        nutrition=NutritionData(
            calories=parsed.calories,
            protein=parsed.protein,
            fat=parsed.fat,
            carbs=parsed.carbs,
        ),
    )


def products_from_parsed(parsed: list[ParsedProduct]) -> list[ProductItem]:
    return [product_from_parsed(p) for p in parsed]


def entry_from_items(
    user_id: int,
    items: list[ProductItem],
    entry_date: date | None,
    tz_name: str | None,
) -> FoodEntry:
    if entry_date and entry_date != time_service.today(tz_name):
        created_at = datetime.combine(entry_date, datetime.min.time())
    else:
        created_at = time_service.now(tz_name)
    return FoodEntry(
        user_id=user_id,
        description=", ".join(item.description for item in items),
        short_description=", ".join(item.short_description or item.description for item in items),
        items=items,
        nutrition=sum_nutrition(items),
        created_at=created_at,
    )


class FoodService:
    def __init__(self, foods: FoodRepository, pending: PendingRepository) -> None:
        self._foods = foods
        self._pending = pending

    # ── Pending-флоу ─────────────────────────────────────

    async def get_pending(self, user_id: int) -> PendingMeal | None:
        return await self._pending.get(user_id)

    async def start_pending(
        self, user_id: int, products: list[ProductItem], entry_date: date | None,
    ) -> PendingMeal:
        meal = PendingMeal(user_id=user_id, items=products, entry_date=entry_date)
        await self._pending.set(meal)
        logger.info("user=%s pending продуктов: %d, date=%s", user_id, len(meal.items), entry_date)
        return meal

    async def append_pending(
        self, user_id: int, products: list[ProductItem], entry_date: date | None,
    ) -> PendingMeal:
        meal = await self._pending.get(user_id)
        if meal is None:
            return await self.start_pending(user_id, products, entry_date)
        meal.items.extend(products)
        if entry_date is not None:
            meal.entry_date = entry_date
        await self._pending.set(meal)
        return meal

    async def remove_pending_item(
        self, user_id: int, index: int,
    ) -> tuple[ProductItem | None, PendingMeal | None]:
        """Возвращает (удалённый продукт, остаток). Остаток None = список опустел."""
        meal = await self._pending.get(user_id)
        if meal is None or index >= len(meal.items):
            return None, meal
        removed = meal.items.pop(index)
        logger.info("user=%s убрал из pending: %s", user_id, removed.description)
        if not meal.items:
            await self._pending.clear(user_id)
            return removed, None
        await self._pending.set(meal)
        return removed, meal

    async def cancel_pending(self, user_id: int) -> None:
        await self._pending.clear(user_id)
        logger.info("user=%s отменил pending", user_id)

    async def confirm_pending(self, user_id: int, tz_name: str | None) -> tuple[str, FoodEntry] | None:
        meal = await self._pending.get(user_id)
        if meal is None or not meal.items:
            return None
        await self._pending.clear(user_id)
        entry = entry_from_items(user_id, meal.items, meal.entry_date, tz_name)
        entry_id = await self._foods.save(entry)
        logger.info("user=%s подтвердил %d продуктов", user_id, len(meal.items))
        return entry_id, entry

    # ── Записи ───────────────────────────────────────────

    async def record_items(
        self,
        user_id: int,
        items: list[ProductItem],
        entry_date: date | None,
        tz_name: str | None,
    ) -> tuple[str, FoodEntry]:
        """Сохраняет приём пищи сразу, минуя pending-подтверждение."""
        entry = entry_from_items(user_id, items, entry_date, tz_name)
        entry_id = await self._foods.save(entry)
        return entry_id, entry

    async def get_entry_by_id(self, entry_id: str, user_id: int) -> FoodEntry | None:
        return await self._foods.get_by_id(entry_id, user_id)

    async def get_entries(self, user_id: int, day: date) -> list[tuple[str, FoodEntry]]:
        return await self._foods.get_for_day(user_id, day)

    async def find_entry(self, user_id: int, day: date, entry_id: str) -> FoodEntry | None:
        for eid, entry in await self._foods.get_for_day(user_id, day):
            if eid == entry_id:
                return entry
        return None

    async def delete_entry(self, entry_id: str, user_id: int) -> bool:
        return await self._foods.delete(entry_id, user_id)

    async def clear_day(self, user_id: int, day: date) -> int:
        return await self._foods.clear_day(user_id, day)
