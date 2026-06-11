import asyncio
import logging
from typing import Any

import aiohttp

from app.models import ProductInfo

logger = logging.getLogger(__name__)

API_URL = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
USER_AGENT = "CALorieTrackerBot/1.0 (Telegram bot)"
KCAL_PER_KJ = 1 / 4.184


def parse_product(barcode: str, data: dict[str, Any]) -> ProductInfo | None:
    """Разбирает ответ OpenFoodFacts. None — продукт не найден или нет КБЖУ."""
    if data.get("status") != 1:
        return None
    product = data.get("product") or {}
    nutriments = product.get("nutriments") or {}

    kcal = nutriments.get("energy-kcal_100g")
    if kcal is None:
        kj = nutriments.get("energy_100g")
        if kj is not None:
            kcal = kj * KCAL_PER_KJ

    name = product.get("product_name_ru") or product.get("product_name") or f"Продукт {barcode}"
    brands = product.get("brands")
    if brands:
        brand = brands.split(",")[0].strip()
        if brand and brand.lower() not in name.lower():
            name = f"{name} ({brand})"

    package_grams: float | None = None
    quantity = product.get("product_quantity")
    unit = (product.get("product_quantity_unit") or "g").lower()
    if quantity and unit in ("g", "ml"):
        try:
            package_grams = float(quantity)
            if package_grams <= 0:
                package_grams = None
        except (ValueError, TypeError):
            package_grams = None

    return ProductInfo(
        barcode=barcode,
        name=name,
        calories_100g=float(kcal) if kcal is not None else None,
        protein_100g=float(nutriments.get("proteins_100g") or 0),
        fat_100g=float(nutriments.get("fat_100g") or 0),
        carbs_100g=float(nutriments.get("carbohydrates_100g") or 0),
        package_grams=package_grams,
    )


class OpenFoodFactsClient:
    async def fetch(self, barcode: str) -> ProductInfo | None:
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    API_URL.format(barcode=barcode),
                    headers={"User-Agent": USER_AGENT},
                ) as resp:
                    if resp.status != 200:
                        logger.info("OFF: штрих-код %s — HTTP %d", barcode, resp.status)
                        return None
                    data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning("OFF недоступен для %s: %s", barcode, e)
            return None

        info = parse_product(barcode, data)
        if info is None:
            logger.info("OFF: штрих-код %s → не найден", barcode)
        elif info.calories_100g is None:
            logger.info("OFF: штрих-код %s → %s (без КБЖУ)", barcode, info.name)
        else:
            logger.info("OFF: штрих-код %s → %s", barcode, info.name)
        return info
