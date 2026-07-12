from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from backend.app.config.defaults import (
    DEFAULT_INCREMENTAL_REPROCESS_DAYS,
    DEFAULT_INGESTION_DEPTH_DAYS,
)
from backend.app.ingestion.planner import IngestionChunk
from backend.app.ingestion.time_rewriter import rewrite_query_time_range

CAPTURE_WAIT_SECONDS = 35


@dataclass(frozen=True)
class IngestionRange:
    mode: Literal["backfill", "incremental"]
    start: datetime
    end: datetime
    latest_source_end: datetime | None
    lookback_days: int = DEFAULT_INCREMENTAL_REPROCESS_DAYS
    range_key: str = "today"
    timezone: str = "CST"
    capture_mode: Literal["daily", "range_contract"] = "daily"

    def details(self) -> dict[str, str | int | None]:
        return {
            "mode": self.mode,
            "start": _iso(self.start),
            "end": _iso(self.end),
            "latest_source_end": _iso(self.latest_source_end) if self.latest_source_end else None,
            "lookback_days": self.lookback_days,
            "range_key": self.range_key,
            "timezone": self.timezone,
            "capture_mode": self.capture_mode,
        }


def build_ingestion_range(
    latest_source_end: datetime | None,
    *,
    now: datetime | None = None,
    depth_days: int = DEFAULT_INGESTION_DEPTH_DAYS,
    incremental_reprocess_days: int = DEFAULT_INCREMENTAL_REPROCESS_DAYS,
) -> IngestionRange:
    end = _as_utc(now or datetime.now(UTC))
    bounded_depth = max(1, depth_days)
    bounded_reprocess = max(0, incremental_reprocess_days)
    if latest_source_end is None:
        return IngestionRange(
            mode="backfill",
            start=end - timedelta(days=bounded_depth),
            end=end,
            latest_source_end=None,
            lookback_days=bounded_depth,
            range_key="today",
        )

    latest = _as_utc(latest_source_end)
    target_floor = end - timedelta(days=bounded_depth)
    reprocess_start = min(latest, end) - timedelta(days=bounded_reprocess)
    start = max(target_floor, reprocess_start)
    if end < start:
        end = start
    return IngestionRange(
        mode="incremental",
        start=start,
        end=end,
        latest_source_end=latest,
        lookback_days=bounded_reprocess,
        range_key="today",
    )


def apply_ingestion_range(
    payload: dict[str, Any],
    ingestion_range: IngestionRange,
) -> tuple[dict[str, Any], bool]:
    chunk = IngestionChunk(
        start=ingestion_range.start,
        end=ingestion_range.end,
        label=f"{_iso(ingestion_range.start)} -> {_iso(ingestion_range.end)}",
    )
    result = rewrite_query_time_range(payload, chunk, timezone=ingestion_range.timezone)
    if result.changed:
        return result.payload, True
    rewritten = deepcopy(payload)
    changed = _rewrite_ts(rewritten, ingestion_range)
    return rewritten, changed


def _rewrite_ts(value: Any, ingestion_range: IngestionRange) -> bool:
    changed = False
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "ts" and _is_ts_window(child):
                value[key] = [
                    _format_like(child[0], ingestion_range.start),
                    _format_like(child[1], ingestion_range.end),
                ]
                changed = True
            elif _rewrite_ts(child, ingestion_range):
                changed = True
    elif isinstance(value, list):
        for child in value:
            if _rewrite_ts(child, ingestion_range):
                changed = True
    return changed


def _is_ts_window(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 2


def _format_like(template: Any, value: datetime) -> str | int | float:
    value = _as_utc(value)
    if isinstance(template, int):
        return int(_epoch_like(template, value))
    if isinstance(template, float):
        return float(_epoch_like(template, value))
    if isinstance(template, str) and template.isdigit():
        return str(int(_epoch_like(int(template), value)))
    return _iso(value)


def _epoch_like(template: int | float, value: datetime) -> int:
    timestamp = value.timestamp()
    return round(timestamp * 1000) if abs(template) > 10_000_000_000 else round(timestamp)


def _iso(value: datetime) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
