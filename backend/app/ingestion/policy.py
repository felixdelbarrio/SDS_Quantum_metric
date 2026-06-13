from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

CAPTURE_WAIT_SECONDS = 35
INCREMENTAL_LOOKBACK_DAYS = 7
FULL_BACKFILL_START = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class IngestionRange:
    mode: Literal["backfill", "incremental"]
    start: datetime
    end: datetime
    latest_source_end: datetime | None
    lookback_days: int = INCREMENTAL_LOOKBACK_DAYS

    def details(self) -> dict[str, str | int | None]:
        return {
            "mode": self.mode,
            "start": _iso(self.start),
            "end": _iso(self.end),
            "latest_source_end": _iso(self.latest_source_end) if self.latest_source_end else None,
            "lookback_days": self.lookback_days,
        }


def build_ingestion_range(
    latest_source_end: datetime | None,
    *,
    now: datetime | None = None,
) -> IngestionRange:
    end = _as_utc(now or datetime.now(UTC))
    if latest_source_end is None:
        return IngestionRange(
            mode="backfill",
            start=FULL_BACKFILL_START,
            end=end,
            latest_source_end=None,
        )

    latest = _as_utc(latest_source_end)
    start = max(FULL_BACKFILL_START, latest - timedelta(days=INCREMENTAL_LOOKBACK_DAYS))
    if end < start:
        end = start
    return IngestionRange(
        mode="incremental",
        start=start,
        end=end,
        latest_source_end=latest,
    )


def apply_ingestion_range(
    payload: dict[str, Any],
    ingestion_range: IngestionRange,
) -> tuple[dict[str, Any], bool]:
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
