"""Время в часовом поясе пользователя.

В БД datetime хранятся наивными, в локальном времени пользователя —
так исторические записи остаются валидными без миграции.
"""

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.config import settings

logger = logging.getLogger(__name__)

# (IANA, подпись для UI)
TIMEZONE_CHOICES: list[tuple[str, str]] = [
    ("Europe/Moscow", "Москва (UTC+3)"),
    ("Europe/Kyiv", "Киев (UTC+2/3)"),
    ("Asia/Yekaterinburg", "Екатеринбург (UTC+5)"),
    ("Asia/Almaty", "Алматы (UTC+5)"),
    ("Asia/Tashkent", "Ташкент (UTC+5)"),
    ("Asia/Bishkek", "Бишкек (UTC+6)"),
    ("Asia/Novosibirsk", "Новосибирск (UTC+7)"),
    ("Asia/Dubai", "Дубай (UTC+4)"),
]


def get_tz(tz_name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name or settings.DEFAULT_TZ)
    except (KeyError, ValueError):
        logger.warning("Неизвестная таймзона %r, используется %s", tz_name, settings.DEFAULT_TZ)
        return ZoneInfo(settings.DEFAULT_TZ)


def now(tz_name: str | None = None) -> datetime:
    """Наивный datetime в часовом поясе пользователя."""
    return datetime.now(get_tz(tz_name)).replace(tzinfo=None)


def today(tz_name: str | None = None) -> date:
    return now(tz_name).date()


def tz_label(tz_name: str | None) -> str:
    name = tz_name or settings.DEFAULT_TZ
    for iana, label in TIMEZONE_CHOICES:
        if iana == name:
            return label
    return name
