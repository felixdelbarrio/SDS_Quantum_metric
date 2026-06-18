from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel

from backend.app.quantum_dashboard.periods import parse_date, zoneinfo_for
from backend.app.storage.parquet_store import ParquetStore


class RangeResolution(BaseModel):
    country: str
    range_key: str
    start: datetime
    end: datetime
    timezone: str
    required_days: list[date]
    covered_days: list[date]
    missing_days: list[date]
    completeness: Literal["complete", "partial", "empty"]
    warning_level: Literal["none", "info", "warning", "blocking"]
    message: str


def resolve_range(
    store: ParquetStore,
    country: str,
    *,
    range_key: str,
    start: str | date | datetime | None,
    end: str | date | datetime | None,
    timezone: str = "CST",
    now: datetime | None = None,
) -> RangeResolution:
    zone = zoneinfo_for(timezone)
    today = (now.astimezone(zone) if now else datetime.now(zone)).date()
    start_day = parse_date(start)
    end_day = parse_date(end)
    if start_day is None and end_day is None:
        start_day, end_day = _default_window(range_key, today)
    start_day = start_day or end_day or today
    end_day = end_day or start_day
    if end_day < start_day:
        start_day, end_day = end_day, start_day

    required_days = _required_days(range_key, start_day, end_day, today)
    coverage = store.day_coverage(country, start_day, end_day)
    covered_days = [day for day in _dates(coverage.get("covered_days")) if day in required_days]
    missing_days = [day for day in required_days if day not in set(covered_days)]
    completeness = _completeness(covered_days, missing_days)
    warning_level = _warning_level(range_key, today, covered_days, missing_days)
    return RangeResolution(
        country=country,
        range_key=range_key,
        start=datetime.combine(start_day, datetime.min.time(), tzinfo=zone),
        end=datetime.combine(end_day, datetime.max.time().replace(microsecond=0), tzinfo=zone),
        timezone=timezone,
        required_days=required_days,
        covered_days=covered_days,
        missing_days=missing_days,
        completeness=completeness,
        warning_level=warning_level,
        message=_message(range_key, warning_level, missing_days),
    )


def range_resolution_payload(resolution: RangeResolution) -> dict[str, Any]:
    payload = resolution.model_dump(mode="json")
    payload["complete"] = resolution.completeness == "complete"
    return payload


def _default_window(range_key: str, today: date) -> tuple[date, date]:
    if range_key == "yesterday":
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday
    if range_key == "last_7_days":
        return today - timedelta(days=6), today
    return today, today


def _required_days(range_key: str, start: date, end: date, today: date) -> list[date]:
    days = [start + timedelta(days=index) for index in range((end - start).days + 1)]
    if range_key == "today":
        return [today] if start <= today <= end else days
    return days


def _dates(values: object) -> list[date]:
    if not isinstance(values, list):
        return []
    parsed = [parse_date(value) for value in values]
    return [value for value in parsed if value is not None]


def _completeness(
    covered_days: list[date], missing_days: list[date]
) -> Literal["complete", "partial", "empty"]:
    if not missing_days:
        return "complete"
    if covered_days:
        return "partial"
    return "empty"


def _warning_level(
    range_key: str,
    today: date,
    covered_days: list[date],
    missing_days: list[date],
) -> Literal["none", "info", "warning", "blocking"]:
    if not missing_days:
        return "none"
    if range_key == "today":
        return "info"
    if missing_days == [today] and today in covered_days:
        return "info"
    return "warning"


def _message(
    range_key: str,
    warning_level: str,
    missing_days: list[date],
) -> str:
    if warning_level == "none":
        return "Periodo completo en persistencia local."
    if range_key == "today":
        return "Today tiene cobertura parcial local; puedes actualizarlo manualmente."
    if len(missing_days) == 1:
        return f"Falta 1 dia para completar el periodo: {missing_days[0].isoformat()}."
    return f"Faltan {len(missing_days)} dias para completar el periodo."
