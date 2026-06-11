from dataclasses import dataclass, field
from datetime import date, timedelta

from app.models import DailyProfileSnapshot, FoodEntry, NutritionData, UserProfile, WorkoutEntry
from app.repositories import FoodRepository, ProfileRepository, WorkoutRepository
from app.services.nutrition import add_nutrition, calc_bmr, calc_target_calories


def week_bounds(ref: date) -> tuple[date, date]:
    start = ref - timedelta(days=ref.weekday())  # Monday
    end = start + timedelta(days=6)  # Sunday
    return start, end


@dataclass
class DaySummary:
    day: date
    entries: list[tuple[str, FoodEntry]]
    total: NutritionData
    workouts: list[tuple[str, WorkoutEntry]] = field(default_factory=list)
    bmr: float | None = None  # None = нет профиля/снимка
    target: float | None = None  # дневная норма (BMR × активность × цель), None = не настроена

    @property
    def burned(self) -> float:
        return sum(w.calories for _, w in self.workouts)

    @property
    def allowance(self) -> float | None:
        """Норма на день: target, а если активность/цель не указаны — BMR."""
        return self.target if self.target is not None else self.bmr

    @property
    def diff(self) -> float | None:
        """Съедено минус (норма + тренировки). Отрицательное = осталось."""
        if self.allowance is None:
            return None
        return self.total.calories - (self.allowance + self.burned)


@dataclass
class WeekDayLine:
    day: date
    nutrition: NutritionData | None  # None = нет записей


@dataclass
class WeekSummary:
    start: date
    end: date
    days: list[WeekDayLine] = field(default_factory=list)
    total: NutritionData = field(default_factory=lambda: NutritionData(calories=0, protein=0, fat=0, carbs=0))
    total_burned: float = 0.0
    total_deficit: float = 0.0
    days_with_bmr: int = 0


class StatsService:
    def __init__(
        self,
        foods: FoodRepository,
        workouts: WorkoutRepository,
        profiles: ProfileRepository,
    ) -> None:
        self._foods = foods
        self._workouts = workouts
        self._profiles = profiles

    async def day_summary(self, user_id: int, day: date) -> DaySummary:
        entries = await self._foods.get_for_day(user_id, day)
        total = NutritionData(calories=0, protein=0, fat=0, carbs=0)
        for _, e in entries:
            add_nutrition(total, e.nutrition)

        workouts = await self._workouts.get_for_day(user_id, day)
        summary = DaySummary(day=day, entries=entries, total=total, workouts=workouts)

        snapshot = await self._profiles.get_snapshot(user_id, day)
        if snapshot:
            profile = await self._profiles.get_profile(user_id)
            if profile:
                summary.bmr = calc_bmr(snapshot.weight, snapshot.height, snapshot.age, profile.gender)
                summary.target = _day_target(summary.bmr, snapshot, profile)
        return summary

    async def week_summary(self, user_id: int, ref: date) -> WeekSummary:
        start, end = week_bounds(ref)
        entries = await self._foods.get_range(user_id, start, end)
        workout_entries = await self._workouts.get_range(user_id, start, end)
        profile = await self._profiles.get_profile(user_id)

        daily: dict[date, NutritionData] = {}
        for _, e in entries:
            day = e.created_at.date()
            if day not in daily:
                daily[day] = NutritionData(calories=0, protein=0, fat=0, carbs=0)
            add_nutrition(daily[day], e.nutrition)

        daily_burned: dict[date, float] = {}
        for _, w in workout_entries:
            day = w.created_at.date()
            daily_burned[day] = daily_burned.get(day, 0) + w.calories

        summary = WeekSummary(start=start, end=end)
        for i in range(7):
            day = start + timedelta(days=i)
            n = daily.get(day)
            summary.days.append(WeekDayLine(day=day, nutrition=n))
            if n is None:
                continue
            add_nutrition(summary.total, n)
            if profile:
                snap = await self._profiles.get_snapshot(user_id, day)
                if snap:
                    bmr = calc_bmr(snap.weight, snap.height, snap.age, profile.gender)
                    allowance = _day_target(bmr, snap, profile) or bmr
                    burned = daily_burned.get(day, 0)
                    summary.total_burned += burned
                    summary.total_deficit += n.calories - (allowance + burned)
                    summary.days_with_bmr += 1
        return summary


def _day_target(bmr: float, snapshot: DailyProfileSnapshot, profile: UserProfile) -> float | None:
    """Норма дня. Старые снимки без активности/цели берут текущие значения профиля."""
    activity = snapshot.activity_level or profile.activity_level
    goal = snapshot.goal or profile.goal
    return calc_target_calories(bmr, activity, goal)
