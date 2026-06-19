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
    data_quality: Literal["missing_days", "range_mismatch", "regression_failed", "complete"]
    warning_level: Literal["none", "info", "warning", "error"]
    last_regression_status: Literal["passed", "failed", "not_run"]
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
    last_regression_status: str | None = None,
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
    regression_status = _regression_status(last_regression_status)
    data_quality = _data_quality(missing_days, regression_status)
    warning_level = _warning_level(range_key, missing_days, data_quality)
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
        data_quality=data_quality,
        warning_level=warning_level,
        last_regression_status=regression_status,
        message=_message(range_key, warning_level, missing_days, data_quality),
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
    missing_days: list[date],
    data_quality: str,
) -> Literal["none", "info", "warning", "error"]:
    if data_quality == "regression_failed":
        return "error"
    if not missing_days:
        return "none"
    if range_key == "today":
        return "info"
    return "warning"


def _message(
    range_key: str,
    warning_level: str,
    missing_days: list[date],
    data_quality: str,
) -> str:
    if data_quality == "regression_failed":
        return "El periodo tiene datos locales, pero la regresion Web vs Local no ha pasado."
    if warning_level == "none":
        return "Periodo completo en persistencia local."
    if range_key == "today":
        return "Today tiene cobertura parcial local; puedes actualizarlo manualmente."
    if len(missing_days) == 1:
        return f"Falta 1 dia para completar el periodo: {missing_days[0].isoformat()}."
    return f"Faltan {len(missing_days)} dias para completar el periodo."


def _regression_status(value: str | None) -> Literal["passed", "failed", "not_run"]:
    if value in {"passed", "passed_with_tolerance"}:
        return "passed"
    if value:
        return "failed"
    return "not_run"


def _data_quality(
    missing_days: list[date],
    regression_status: Literal["passed", "failed", "not_run"],
) -> Literal["missing_days", "range_mismatch", "regression_failed", "complete"]:
    if missing_days:
        return "missing_days"
    if regression_status == "failed":
        return "regression_failed"
    return "complete"
