import logging
from datetime import date, datetime

from app.models import WorkoutEntry
from app.repositories import WorkoutRepository
from app.services import time_service

logger = logging.getLogger(__name__)


class WorkoutService:
    def __init__(self, workouts: WorkoutRepository) -> None:
        self._workouts = workouts

    async def add(
        self,
        user_id: int,
        description: str,
        calories: float,
        day: date,
        tz_name: str | None,
    ) -> WorkoutEntry:
        entry = WorkoutEntry(
            user_id=user_id,
            calories=calories,
            description=description,
            created_at=datetime.combine(day, time_service.now(tz_name).time()),
        )
        await self._workouts.save(entry)
        logger.info("user=%s тренировка: %s %.0f ккал", user_id, description, calories)
        return entry

    async def delete(self, entry_id: str, user_id: int) -> bool:
        return await self._workouts.delete(entry_id, user_id)
