from datetime import date, timedelta

from app.models import NutritionData, ProductItem
from app.services import FoodService
from app.services import time_service
from tests.unit.fakes import FakeFoodRepository, FakePendingRepository


def _product(name: str, calories: float) -> ProductItem:
    return ProductItem(
        description=name,
        short_description=name,
        nutrition=NutritionData(calories=calories, protein=1, fat=2, carbs=3),
    )


def _service() -> FoodService:
    return FoodService(FakeFoodRepository(), FakePendingRepository())


async def test_start_and_get_pending():
    svc = _service()
    await svc.start_pending(1, [_product("хлеб", 100)], None)
    meal = await svc.get_pending(1)
    assert meal is not None
    assert len(meal.items) == 1
    assert meal.entry_date is None


async def test_append_pending_keeps_date():
    svc = _service()
    yesterday = date.today() - timedelta(days=1)
    await svc.start_pending(1, [_product("хлеб", 100)], yesterday)
    meal = await svc.append_pending(1, [_product("сыр", 200)], None)
    assert len(meal.items) == 2
    assert meal.entry_date == yesterday  # None не затирает дату


async def test_append_pending_overrides_date():
    svc = _service()
    yesterday = date.today() - timedelta(days=1)
    await svc.start_pending(1, [_product("хлеб", 100)], None)
    meal = await svc.append_pending(1, [_product("сыр", 200)], yesterday)
    assert meal.entry_date == yesterday


async def test_start_pending_multiple_products():
    svc = _service()
    meal = await svc.start_pending(1, [_product("гречка", 150), _product("курица", 250)], None)
    assert len(meal.items) == 2


async def test_products_from_parsed():
    from app.llm.protocol import ParsedProduct
    from app.services.food_service import products_from_parsed

    parsed = [
        ParsedProduct(description="Гречка 150г", short_description="Гречка", grams=150,
                      calories=150, protein=5, fat=1, carbs=30),
        ParsedProduct(description="Курица", short_description="Курица",
                      calories=250, protein=30, fat=12, carbs=0),
    ]
    products = products_from_parsed(parsed)
    assert len(products) == 2
    assert products[0].grams == 150
    assert products[1].nutrition.calories == 250


async def test_remove_pending_item():
    svc = _service()
    await svc.start_pending(1, [_product("хлеб", 100)], None)
    await svc.append_pending(1, [_product("сыр", 200)], None)

    removed, meal = await svc.remove_pending_item(1, 0)
    assert removed is not None and removed.description == "хлеб"
    assert meal is not None and len(meal.items) == 1

    removed, meal = await svc.remove_pending_item(1, 0)
    assert removed is not None
    assert meal is None  # список опустел — pending удалён
    assert await svc.get_pending(1) is None


async def test_remove_pending_item_bad_index():
    svc = _service()
    await svc.start_pending(1, [_product("хлеб", 100)], None)
    removed, _ = await svc.remove_pending_item(1, 5)
    assert removed is None


async def test_confirm_pending_today():
    svc = _service()
    await svc.start_pending(1, [_product("хлеб", 100)], None)
    await svc.append_pending(1, [_product("сыр", 200)], None)

    confirmed = await svc.confirm_pending(1, None)
    assert confirmed is not None
    entry_id, entry = confirmed
    assert entry_id
    assert entry.nutrition.calories == 300
    assert entry.description == "хлеб, сыр"
    assert await svc.get_pending(1) is None

    today = time_service.today(None)
    entries = await svc.get_entries(1, today)
    assert len(entries) == 1


async def test_confirm_pending_past_date_stored_at_midnight():
    svc = _service()
    yesterday = time_service.today(None) - timedelta(days=1)
    await svc.start_pending(1, [_product("плов", 600)], yesterday)

    confirmed = await svc.confirm_pending(1, None)
    assert confirmed is not None
    _, entry = confirmed
    assert entry.created_at.date() == yesterday
    assert entry.created_at.hour == 0 and entry.created_at.minute == 0


async def test_confirm_without_pending_returns_none():
    svc = _service()
    assert await svc.confirm_pending(1, None) is None


async def test_cancel_pending():
    svc = _service()
    await svc.start_pending(1, [_product("хлеб", 100)], None)
    await svc.cancel_pending(1)
    assert await svc.get_pending(1) is None
