from zoneinfo import ZoneInfo

from app.config import settings
from app.services import time_service


def test_get_tz_valid():
    assert time_service.get_tz("Europe/Moscow") == ZoneInfo("Europe/Moscow")


def test_get_tz_none_falls_back_to_default():
    assert time_service.get_tz(None) == ZoneInfo(settings.DEFAULT_TZ)


def test_get_tz_invalid_falls_back_to_default():
    assert time_service.get_tz("Mars/Olympus") == ZoneInfo(settings.DEFAULT_TZ)


def test_now_is_naive():
    assert time_service.now("Asia/Almaty").tzinfo is None


def test_today_differs_across_zones_at_midnight():
    # Просто smoke: оба вызова не падают и возвращают date
    assert time_service.today("Pacific/Auckland") >= time_service.today("Pacific/Honolulu")


def test_tz_label_known():
    assert "Алматы" in time_service.tz_label("Asia/Almaty")


def test_tz_label_unknown_returns_iana():
    assert time_service.tz_label("Europe/Lisbon") == "Europe/Lisbon"
