from datetime import date, datetime

from app.models import (
    DailyProfileSnapshot,
    FoodEntry,
    NutritionData,
    UserProfile,
    WorkoutEntry,
)
from app.services import StatsService
from app.services.stats_service import week_bounds
from tests.unit.fakes import FakeFoodRepository, FakeProfileRepository, FakeWorkoutRepository

USER = 1
DAY = date(2026, 6, 10)  # среда


def _entry(calories: float, created_at: datetime) -> FoodEntry:
    return FoodEntry(
        user_id=USER,
        description="еда",
        nutrition=NutritionData(calories=calories, protein=10, fat=5, carbs=20),
        created_at=created_at,
    )


def _setup() -> tuple[StatsService, FakeFoodRepository, FakeWorkoutRepository, FakeProfileRepository]:
    foods = FakeFoodRepository()
    workouts = FakeWorkoutRepository()
    profiles = FakeProfileRepository()
    return StatsService(foods, workouts, profiles), foods, workouts, profiles


def test_week_bounds_monday_to_sunday():
    start, end = week_bounds(DAY)
    assert start == date(2026, 6, 8)
    assert end == date(2026, 6, 14)
    assert start.weekday() == 0
    assert end.weekday() == 6


def test_week_bounds_on_monday():
    monday = date(2026, 6, 8)
    start, end = week_bounds(monday)
    assert start == monday


async def test_day_summary_no_profile():
    svc, foods, _, _ = _setup()
    await foods.save(_entry(500, datetime(2026, 6, 10, 12, 0)))

    summary = await svc.day_summary(USER, DAY)
    assert summary.total.calories == 500
    assert summary.bmr is None
    assert summary.diff is None


async def test_day_summary_with_profile_and_workout():
    svc, foods, workouts, profiles = _setup()
    await foods.save(_entry(1500, datetime(2026, 6, 10, 12, 0)))
    await foods.save(_entry(500, datetime(2026, 6, 10, 18, 0)))
    await profiles.upsert_profile(UserProfile(user_id=USER, gender="male", weight=80, height=180, age=30))
    await profiles.upsert_snapshot(DailyProfileSnapshot(user_id=USER, weight=80, height=180, age=30, date=DAY))
    await workouts.save(WorkoutEntry(
        user_id=USER, calories=300, description="бег", created_at=datetime(2026, 6, 10, 8, 0),
    ))

    summary = await svc.day_summary(USER, DAY)
    assert summary.total.calories == 2000
    assert summary.bmr == 1780  # 10*80 + 6.25*180 - 5*30 + 5
    assert summary.burned == 300
    assert summary.diff == 2000 - (1780 + 300)  # -80 → дефицит


async def test_day_summary_with_activity_and_goal_uses_target():
    svc, foods, _, profiles = _setup()
    await foods.save(_entry(2000, datetime(2026, 6, 10, 12, 0)))
    await profiles.upsert_profile(UserProfile(
        user_id=USER, gender="male", weight=80, height=180, age=30,
        activity_level="moderate", goal="lose",
    ))
    await profiles.upsert_snapshot(DailyProfileSnapshot(
        user_id=USER, weight=80, height=180, age=30, date=DAY,
        activity_level="moderate", goal="lose",
    ))

    summary = await svc.day_summary(USER, DAY)
    target = 1780 * 1.55 * 0.85  # BMR × активность × цель
    assert summary.target == target
    assert summary.allowance == target
    assert summary.diff == 2000 - target


async def test_day_summary_old_snapshot_falls_back_to_profile_activity():
    """Снимок без активности/цели берёт текущие значения профиля."""
    svc, foods, _, profiles = _setup()
    await foods.save(_entry(2000, datetime(2026, 6, 10, 12, 0)))
    await profiles.upsert_profile(UserProfile(
        user_id=USER, gender="male", weight=80, height=180, age=30,
        activity_level="sedentary", goal="maintain",
    ))
    await profiles.upsert_snapshot(DailyProfileSnapshot(
        user_id=USER, weight=80, height=180, age=30, date=DAY,
    ))

    summary = await svc.day_summary(USER, DAY)
    assert summary.target == 1780 * 1.2


async def test_day_summary_no_activity_falls_back_to_bmr():
    svc, foods, _, profiles = _setup()
    await foods.save(_entry(2000, datetime(2026, 6, 10, 12, 0)))
    await profiles.upsert_profile(UserProfile(user_id=USER, gender="male", weight=80, height=180, age=30))
    await profiles.upsert_snapshot(DailyProfileSnapshot(user_id=USER, weight=80, height=180, age=30, date=DAY))

    summary = await svc.day_summary(USER, DAY)
    assert summary.target is None
    assert summary.allowance == 1780  # BMR
    assert summary.diff == 2000 - 1780


async def test_day_summary_includes_workouts_without_profile():
    """Тренировки видны в сводке дня даже без профиля."""
    svc, _, workouts, _ = _setup()
    await workouts.save(WorkoutEntry(
        user_id=USER, calories=300, description="бег", created_at=datetime(2026, 6, 10, 8, 0),
    ))

    summary = await svc.day_summary(USER, DAY)
    assert len(summary.workouts) == 1
    assert summary.burned == 300
    assert summary.bmr is None


async def test_week_summary_aggregates():
    svc, foods, workouts, profiles = _setup()
    await profiles.upsert_profile(UserProfile(user_id=USER, gender="male", weight=80, height=180, age=30))
    for d in (date(2026, 6, 8), date(2026, 6, 9)):
        await profiles.upsert_snapshot(DailyProfileSnapshot(user_id=USER, weight=80, height=180, age=30, date=d))
        await foods.save(_entry(1800, datetime(d.year, d.month, d.day, 13, 0)))
    await workouts.save(WorkoutEntry(
        user_id=USER, calories=200, description="бег", created_at=datetime(2026, 6, 9, 7, 0),
    ))

    summary = await svc.week_summary(USER, DAY)
    assert summary.start == date(2026, 6, 8)
    assert len(summary.days) == 7
    assert summary.total.calories == 3600
    assert summary.days_with_bmr == 2
    assert summary.total_burned == 200
    # день 1: 1800-1780=20; день 2: 1800-(1780+200)=-180 → итого -160
    assert summary.total_deficit == -160
    assert summary.days[0].nutrition is not None
    assert summary.days[2].nutrition is None  # среда без записей
