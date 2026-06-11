import io
import logging
from typing import Protocol

import zxingcpp
from PIL import Image

from app.models import NutritionData, ProductInfo, ProductItem
from app.repositories.product_cache_repo import ProductCacheRepository

logger = logging.getLogger(__name__)

# Только товарные коды — QR и прочее не интересуют
PRODUCT_FORMATS = (
    zxingcpp.BarcodeFormat.EAN13
    | zxingcpp.BarcodeFormat.EAN8
    | zxingcpp.BarcodeFormat.UPCA
    | zxingcpp.BarcodeFormat.UPCE
)


class ProductClient(Protocol):
    async def fetch(self, barcode: str) -> ProductInfo | None: ...


class BarcodeService:
    def __init__(self, client: ProductClient, cache: ProductCacheRepository) -> None:
        self._client = client
        self._cache = cache

    @staticmethod
    def decode(image: bytes) -> str | None:
        """Ищет товарный штрих-код на фото. None — не найден."""
        try:
            img = Image.open(io.BytesIO(image))
            results = zxingcpp.read_barcodes(img, formats=PRODUCT_FORMATS)
        except Exception as e:  # битое изображение и т.п.
            logger.warning("Ошибка декодирования штрих-кода: %s", e)
            return None
        if not results:
            return None
        barcode = results[0].text
        logger.info("Найден штрих-код: %s", barcode)
        return barcode

    async def lookup(self, barcode: str) -> ProductInfo | None:
        cached = await self._cache.get(barcode)
        if cached:
            return cached
        info = await self._client.fetch(barcode)
        # Карточки без КБЖУ не кэшируем — данные в OFF могут дозаполнить
        if info and info.calories_100g is not None:
            await self._cache.set(info)
        return info

    @staticmethod
    def to_product_item(info: ProductInfo, grams: float) -> ProductItem:
        assert info.calories_100g is not None, "продукт без КБЖУ — нужен LLM-fallback"
        k = grams / 100
        return ProductItem(
            description=f"{info.name} {grams:.0f}г",
            short_description=info.name,
            grams=grams,
            nutrition=NutritionData(
                calories=info.calories_100g * k,
                protein=info.protein_100g * k,
                fat=info.fat_100g * k,
                carbs=info.carbs_100g * k,
            ),
        )
