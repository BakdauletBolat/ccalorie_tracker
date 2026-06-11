from datetime import datetime

from pydantic import BaseModel


class WorkoutEntry(BaseModel):
    user_id: int
    calories: float
    description: str
    created_at: datetime
