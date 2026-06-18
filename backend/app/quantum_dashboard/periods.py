from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

MEXICO_ZONE = ZoneInfo("America/Mexico_City")


def format_period_label(
    start: datetime,
    end: datetime,
    timezone: str,
    preset: str | None = None,
) -> str:
    zone = zoneinfo_for(timezone)
    start_local = start.astimezone(zone)
    end_local = end.astimezone(zone)
    normalized_preset = _infer_preset(start_local, end_local, preset)
    range_text = _format_range(start_local, end_local, timezone)
    if normalized_preset == "today":
        return f"Today ({range_text})"
    if normalized_preset == "yesterday":
        return f"Yesterday ({range_text})"
    if normalized_preset == "last_7_days":
        return (
            f"{_format_date(start_local.date())} - "
            f"{_format_date(end_local.date())} ({label_for_timezone(timezone)})"
        )
    if start_local.date() == end_local.date():
        return (
            f"{_format_date(start_local.date())} "
            f"({_format_time(start_local)} - "
            f"{_format_time(end_local)} {label_for_timezone(timezone)})"
        )
    return (
        f"{_format_date(start_local.date())} - "
        f"{_format_date(end_local.date())} ({label_for_timezone(timezone)})"
    )


def period_bounds_for_dates(
    start_date: str | None,
    end_date: str | None,
    *,
    timezone: str = "CST",
) -> tuple[datetime | None, datetime | None, str | None]:
    start_day = parse_date(start_date)
    end_day = parse_date(end_date)
    if not start_day and not end_day:
        return None, None, None
    start_day = start_day or end_day
    end_day = end_day or start_day
    if start_day is None or end_day is None:
        return None, None, None
    if end_day < start_day:
        start_day, end_day = end_day, start_day
    zone = zoneinfo_for(timezone)
    start = datetime.combine(start_day, time.min, tzinfo=zone).astimezone(UTC)
    end = datetime.combine(end_day, time.max.replace(microsecond=0), tzinfo=zone).astimezone(UTC)
    preset = infer_preset_for_dates(start_day, end_day, timezone=timezone)
    return start, end, preset


def infer_preset_for_dates(
    start_day: date,
    end_day: date,
    *,
    timezone: str = "CST",
    today: date | None = None,
) -> str:
    current = today or datetime.now(zoneinfo_for(timezone)).date()
    if start_day == current and end_day == current:
        return "today"
    if start_day == current - timedelta(days=1) and end_day == start_day:
        return "yesterday"
    if start_day == current - timedelta(days=6) and end_day == current:
        return "last_7_days"
    return "custom"


def parse_datetime(value: Any, timezone: str | None = "CST") -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, int | float):
        timestamp = value / 1000 if abs(value) > 10_000_000_000 else value
        return datetime.fromtimestamp(timestamp, UTC)
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return parse_datetime(int(text), timezone)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        parsed_day = parse_date(text[:10])
        if parsed_day:
            zone = zoneinfo_for(timezone or "CST")
            return datetime.combine(parsed_day, time.min, tzinfo=zone).astimezone(UTC)
    return None


def parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.astimezone(UTC).date()
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        parsed = parse_datetime(value)
        return parsed.date() if parsed else None


def label_for_timezone(timezone: str | None) -> str:
    if not timezone:
        return "CST"
    if timezone == "America/Mexico_City":
        return "CST"
    return timezone


def zoneinfo_for(timezone: str | None) -> ZoneInfo:
    if timezone in {None, "", "CST", "America/Mexico_City"}:
        return MEXICO_ZONE
    if timezone == "UTC":
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(str(timezone))
    except Exception:
        return MEXICO_ZONE


def _infer_preset(start: datetime, end: datetime, preset: str | None) -> str:
    if preset:
        return preset
    return infer_preset_for_dates(start.date(), end.date(), timezone="America/Mexico_City")


def _format_datetime(value: datetime) -> str:
    return f"{_format_date(value.date())}, {_format_time(value)}"


def _format_range(start: datetime, end: datetime, timezone: str) -> str:
    zone_label = label_for_timezone(timezone)
    if start.date() == end.date():
        return (
            f"{_format_date(start.date())}, "
            f"{_format_time(start)} - {_format_time(end)} {zone_label}"
        )
    return f"{_format_datetime(start)} - {_format_datetime(end)} {zone_label}"


def _format_date(value: date) -> str:
    return value.strftime("%b %d, %Y")


def _format_time(value: datetime) -> str:
    hour = value.hour % 12 or 12
    minute = value.minute
    suffix = "am" if value.hour < 12 else "pm"
    return f"{hour}:{minute:02d}{suffix}"
