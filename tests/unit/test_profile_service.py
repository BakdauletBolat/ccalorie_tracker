from datetime import datetime

from app.models import FoodEntry, NutritionData, UserProfile
from app.services import ProfileService
from app.services import time_service
from tests.unit.fakes import FakeFoodRepository, FakeProfileRepository

USER = 1


def _profile(**overrides) -> UserProfile:
    defaults = dict(user_id=USER, gender="male", weight=80, height=180, age=30)
    return UserProfile(**{**defaults, **overrides})


async def test_create_makes_today_snapshot():
    profiles = FakeProfileRepository()
    svc = ProfileService(profiles, FakeFoodRepository())
    await svc.create(_profile())

    today = time_service.today(None)
    snap = await profiles.get_snapshot(USER, today)
    assert snap is not None
    assert snap.weight == 80


async def test_create_backfills_snapshots_for_active_days():
    profiles = FakeProfileRepository()
    foods = FakeFoodRepository()
    await foods.save(FoodEntry(
        user_id=USER, description="еда",
        nutrition=NutritionData(calories=500, protein=1, fat=1, carbs=1),
        created_at=datetime(2026, 6, 1, 12, 0),
    ))
    svc = ProfileService(profiles, foods)
    await svc.create(_profile())

    snap = await profiles.get_snapshot(USER, datetime(2026, 6, 1).date())
    assert snap is not None


async def test_ensure_today_snapshot_returns_profile():
    profiles = FakeProfileRepository()
    svc = ProfileService(profiles, FakeFoodRepository())
    await profiles.upsert_profile(_profile())

    profile = await svc.ensure_today_snapshot(USER)
    assert profile is not None
    snap = await profiles.get_snapshot(USER, time_service.today(None))
    assert snap is not None


async def test_ensure_today_snapshot_no_profile():
    svc = ProfileService(FakeProfileRepository(), FakeFoodRepository())
    assert await svc.ensure_today_snapshot(USER) is None
