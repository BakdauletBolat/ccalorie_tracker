from datetime import datetime

from app.models import FoodEntry, NutritionData, ProductItem
from app.services import FavoriteService
from app.services import time_service
from tests.unit.fakes import FakeFavoriteRepository, FakeFoodRepository

USER = 1


def _entry() -> FoodEntry:
    items = [
        ProductItem(
            description="Овсянка 60г", short_description="Овсянка", grams=60,
            nutrition=NutritionData(calories=220, protein=8, fat=4, carbs=40),
        ),
        ProductItem(
            description="Банан", short_description="Банан",
            nutrition=NutritionData(calories=90, protein=1, fat=0, carbs=23),
        ),
    ]
    return FoodEntry(
        user_id=USER,
        description="Овсянка 60г, Банан",
        short_description="Овсянка, Банан",
        items=items,
        nutrition=NutritionData(calories=310, protein=9, fat=4, carbs=63),
        created_at=datetime(2026, 6, 10, 9, 0),
    )


def _setup() -> tuple[FavoriteService, FakeFoodRepository]:
    foods = FakeFoodRepository()
    return FavoriteService(FakeFavoriteRepository(), foods), foods


async def test_add_from_entry():
    svc, _ = _setup()
    fav_id, dish = await svc.add_from_entry(_entry(), None)
    assert fav_id
    assert dish.name == "Овсянка, Банан"
    assert len(dish.items) == 2
    assert dish.nutrition.calories == 310


async def test_add_same_name_overwrites():
    svc, _ = _setup()
    fav_id1, _ = await svc.add_from_entry(_entry(), None)
    fav_id2, _ = await svc.add_from_entry(_entry(), None)
    assert fav_id1 == fav_id2
    assert len(await svc.list(USER)) == 1


async def test_record_creates_entry_today():
    svc, foods = _setup()
    fav_id, _ = await svc.add_from_entry(_entry(), None)

    entry = await svc.record(fav_id, USER, None)
    assert entry is not None
    assert entry.nutrition.calories == 310
    assert entry.created_at.date() == time_service.today(None)

    saved = await foods.get_for_day(USER, time_service.today(None))
    assert len(saved) == 1


async def test_record_unknown_returns_none():
    svc, _ = _setup()
    assert await svc.record("999", USER, None) is None


async def test_delete():
    svc, _ = _setup()
    fav_id, _ = await svc.add_from_entry(_entry(), None)
    assert await svc.delete(fav_id, USER) is True
    assert await svc.get(fav_id, USER) is None
    assert await svc.delete(fav_id, USER) is False


async def test_record_other_user_denied():
    svc, _ = _setup()
    fav_id, _ = await svc.add_from_entry(_entry(), None)
    assert await svc.record(fav_id, 999, None) is None
