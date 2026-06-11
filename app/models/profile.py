from datetime import date

from pydantic import BaseModel


class UserProfile(BaseModel):
    user_id: int
    gender: str  # "male" / "female"
    weight: float  # кг
    height: float  # см
    age: int
    timezone: str | None = None  # IANA, None = settings.DEFAULT_TZ
    activity_level: str | None = None  # ключ из nutrition.ACTIVITY_FACTORS, None = не указан
    goal: str | None = None  # "lose" / "maintain" / "gain", None = не указана


class DailyProfileSnapshot(BaseModel):
    user_id: int
    weight: float
    height: float
    age: int
    date: date
    activity_level: str | None = None
    goal: str | None = None
