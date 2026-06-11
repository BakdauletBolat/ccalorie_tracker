import logging

from app.models import DailyProfileSnapshot, UserProfile
from app.repositories import FoodRepository, ProfileRepository
from app.services import time_service

logger = logging.getLogger(__name__)


class ProfileService:
    def __init__(self, profiles: ProfileRepository, foods: FoodRepository) -> None:
        self._profiles = profiles
        self._foods = foods

    async def get(self, user_id: int) -> UserProfile | None:
        return await self._profiles.get_profile(user_id)

    async def create(self, profile: UserProfile) -> None:
        """Онбординг: сохранить профиль и создать снимки для всех дней с записями."""
        await self._profiles.upsert_profile(profile)
        await self._snapshot_today(profile)

        active_days = await self._foods.active_days(profile.user_id)
        if active_days:
            snapshots = [
                DailyProfileSnapshot(
                    user_id=profile.user_id, weight=profile.weight,
                    height=profile.height, age=profile.age, date=day,
                    activity_level=profile.activity_level, goal=profile.goal,
                )
                for day in active_days
            ]
            await self._profiles.bulk_upsert_snapshots(snapshots)

    async def update(self, profile: UserProfile) -> None:
        await self._profiles.upsert_profile(profile)
        await self._snapshot_today(profile)

    async def ensure_today_snapshot(self, user_id: int) -> UserProfile | None:
        """Создаёт снимок на сегодня если его нет. Возвращает профиль для переиспользования."""
        profile = await self._profiles.get_profile(user_id)
        if not profile:
            return None
        day = time_service.today(profile.timezone)
        if not await self._profiles.get_snapshot(user_id, day):
            await self._snapshot_today(profile)
        return profile

    async def _snapshot_today(self, profile: UserProfile) -> None:
        await self._profiles.upsert_snapshot(DailyProfileSnapshot(
            user_id=profile.user_id, weight=profile.weight,
            height=profile.height, age=profile.age,
            date=time_service.today(profile.timezone),
            activity_level=profile.activity_level, goal=profile.goal,
        ))
