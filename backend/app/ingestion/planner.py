from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Protocol


class IngestionRangeLike(Protocol):
    @property
    def start(self) -> datetime: ...

    @property
    def end(self) -> datetime: ...


@dataclass(frozen=True)
class IngestionChunk:
    start: datetime
    end: datetime
    label: str

    def details(self) -> dict[str, str]:
        return {
            "start": _iso(self.start),
            "end": _iso(self.end),
            "label": self.label,
        }


def plan_ingestion_chunks(
    ingestion_range: IngestionRangeLike,
    *,
    chunk_days: int = 1,
    now: datetime | None = None,
    newest_first: bool = True,
) -> list[IngestionChunk]:
    bounded_days = max(1, chunk_days)
    current = _as_utc(ingestion_range.start)
    end = _as_utc(ingestion_range.end)
    chunks: list[IngestionChunk] = []
    while current < end:
        chunk_end = min(current + timedelta(days=bounded_days), end)
        chunks.append(
            IngestionChunk(start=current, end=chunk_end, label=_label(current, chunk_end))
        )
        current = chunk_end
    if not chunks and end >= current:
        chunks.append(IngestionChunk(start=current, end=end, label=_label(current, end)))
    return list(reversed(chunks)) if newest_first else chunks


def _label(start: datetime, end: datetime) -> str:
    if start.date() == end.date():
        return start.strftime("%Y-%m-%d")
    return f"{start:%Y-%m-%d} -> {end:%Y-%m-%d}"


def day_bounds(value: datetime) -> tuple[datetime, datetime]:
    day_start = datetime.combine(_as_utc(value).date(), time.min, tzinfo=UTC)
    return day_start, day_start + timedelta(days=1)


def _iso(value: datetime) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
