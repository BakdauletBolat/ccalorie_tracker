"""In-memory реализации репозиториев для юнит-тестов сервисов."""

from datetime import date

from app.models import DailyProfileSnapshot, FavoriteDish, FoodEntry, PendingMeal, UserProfile, WorkoutEntry


class FakeFoodRepository:
    def __init__(self) -> None:
        self._entries: dict[str, FoodEntry] = {}
        self._next_id = 1

    async def save(self, entry: FoodEntry) -> str:
        entry_id = str(self._next_id)
        self._next_id += 1
        self._entries[entry_id] = entry
        return entry_id

    async def get_for_day(self, user_id: int, day: date) -> list[tuple[str, FoodEntry]]:
        return sorted(
            (
                (eid, e) for eid, e in self._entries.items()
                if e.user_id == user_id and e.created_at.date() == day
            ),
            key=lambda pair: pair[1].created_at,
        )

    async def get_range(self, user_id: int, start_day: date, end_day: date) -> list[tuple[str, FoodEntry]]:
        return sorted(
            (
                (eid, e) for eid, e in self._entries.items()
                if e.user_id == user_id and start_day <= e.created_at.date() <= end_day
            ),
            key=lambda pair: pair[1].created_at,
        )

    async def get_by_id(self, entry_id: str, user_id: int) -> FoodEntry | None:
        entry = self._entries.get(entry_id)
        if entry is None or entry.user_id != user_id:
            return None
        return entry

    async def delete(self, entry_id: str, user_id: int) -> bool:
        entry = self._entries.get(entry_id)
        if entry is None or entry.user_id != user_id:
            return False
        del self._entries[entry_id]
        return True

    async def clear_day(self, user_id: int, day: date) -> int:
        ids = [eid for eid, e in await self.get_for_day(user_id, day)]
        for eid in ids:
            del self._entries[eid]
        return len(ids)

    async def active_days(self, user_id: int) -> list[date]:
        days = {e.created_at.date() for e in self._entries.values() if e.user_id == user_id}
        return sorted(days)


class FakeWorkoutRepository:
    def __init__(self) -> None:
        self._entries: dict[str, WorkoutEntry] = {}
        self._next_id = 1

    async def save(self, entry: WorkoutEntry) -> str:
        entry_id = str(self._next_id)
        self._next_id += 1
        self._entries[entry_id] = entry
        return entry_id

    async def get_for_day(self, user_id: int, day: date) -> list[tuple[str, WorkoutEntry]]:
        return [
            (eid, e) for eid, e in self._entries.items()
            if e.user_id == user_id and e.created_at.date() == day
        ]

    async def get_range(self, user_id: int, start_day: date, end_day: date) -> list[tuple[str, WorkoutEntry]]:
        return [
            (eid, e) for eid, e in self._entries.items()
            if e.user_id == user_id and start_day <= e.created_at.date() <= end_day
        ]

    async def delete(self, entry_id: str, user_id: int) -> bool:
        entry = self._entries.get(entry_id)
        if entry is None or entry.user_id != user_id:
            return False
        del self._entries[entry_id]
        return True


class FakeProfileRepository:
    def __init__(self) -> None:
        self._profiles: dict[int, UserProfile] = {}
        self._snapshots: dict[tuple[int, date], DailyProfileSnapshot] = {}

    async def upsert_profile(self, profile: UserProfile) -> None:
        self._profiles[profile.user_id] = profile

    async def get_profile(self, user_id: int) -> UserProfile | None:
        return self._profiles.get(user_id)

    async def upsert_snapshot(self, snapshot: DailyProfileSnapshot) -> None:
        self._snapshots[(snapshot.user_id, snapshot.date)] = snapshot

    async def get_snapshot(self, user_id: int, day: date) -> DailyProfileSnapshot | None:
        return self._snapshots.get((user_id, day))

    async def bulk_upsert_snapshots(self, snapshots: list[DailyProfileSnapshot]) -> int:
        for s in snapshots:
            await self.upsert_snapshot(s)
        return len(snapshots)


class FakeFavoriteRepository:
    def __init__(self) -> None:
        self._dishes: dict[str, FavoriteDish] = {}
        self._next_id = 1

    async def upsert(self, dish: FavoriteDish) -> str:
        for fav_id, existing in self._dishes.items():
            if existing.user_id == dish.user_id and existing.name == dish.name:
                self._dishes[fav_id] = dish
                return fav_id
        fav_id = str(self._next_id)
        self._next_id += 1
        self._dishes[fav_id] = dish
        return fav_id

    async def list(self, user_id: int) -> list[tuple[str, FavoriteDish]]:
        return sorted(
            ((fid, d) for fid, d in self._dishes.items() if d.user_id == user_id),
            key=lambda pair: pair[1].created_at,
            reverse=True,
        )

    async def get(self, fav_id: str, user_id: int) -> FavoriteDish | None:
        dish = self._dishes.get(fav_id)
        if dish is None or dish.user_id != user_id:
            return None
        return dish

    async def delete(self, fav_id: str, user_id: int) -> bool:
        dish = self._dishes.get(fav_id)
        if dish is None or dish.user_id != user_id:
            return False
        del self._dishes[fav_id]
        return True


class FakePendingRepository:
    def __init__(self) -> None:
        self._meals: dict[int, PendingMeal] = {}

    async def get(self, user_id: int) -> PendingMeal | None:
        meal = self._meals.get(user_id)
        # копия — как из БД, чтобы мутации без set() не сохранялись
        return meal.model_copy(deep=True) if meal else None

    async def set(self, meal: PendingMeal) -> None:
        self._meals[meal.user_id] = meal.model_copy(deep=True)

    async def clear(self, user_id: int) -> None:
        self._meals.pop(user_id, None)
