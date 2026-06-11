import logging
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models import ProductInfo

logger = logging.getLogger(__name__)


class ProductCacheRepository:
    """Кэш продуктов по штрих-коду — повторные сканы не ходят в OpenFoodFacts."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:  # type: ignore[type-arg]
        self._col = db.products

    async def get(self, barcode: str) -> ProductInfo | None:
        doc = await self._col.find_one({"barcode": barcode})
        if not doc:
            return None
        return ProductInfo(**doc)

    async def set(self, info: ProductInfo) -> None:
        await self._col.update_one(
            {"barcode": info.barcode},
            {"$set": {**info.model_dump(), "fetched_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
