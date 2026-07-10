from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from backend.app.ingestion.planner import IngestionChunk


@dataclass(frozen=True)
class QueryTimeRange:
    start: datetime
    end: datetime
    timezone: str | None = None
    label: str | None = None


@dataclass(frozen=True)
class RewriteResult:
    payload: dict[str, Any]
    changed: bool
    range: QueryTimeRange


@dataclass(frozen=True)
class RangeValidation:
    status: str
    requested_start: datetime
    requested_end: datetime
    extracted_start: datetime | None
    extracted_end: datetime | None
    error: str | None = None


def rewrite_query_time_range(
    payload: dict[str, Any], target: IngestionChunk, *, timezone: str = "CST"
) -> RewriteResult:
    rewritten = deepcopy(payload)
    changed = _rewrite(rewritten, target)
    return RewriteResult(
        payload=rewritten,
        changed=changed,
        range=QueryTimeRange(
            start=target.start, end=target.end, timezone=timezone, label=target.label
        ),
    )


def validate_query_time_range(payload: dict[str, Any], target: IngestionChunk) -> RangeValidation:
    extracted = extract_query_time_range(payload)
    if extracted is None:
        return RangeValidation(
            status="failed",
            requested_start=target.start,
            requested_end=target.end,
            extracted_start=None,
            extracted_end=None,
            error="No time range could be extracted after rewrite.",
        )
    tolerance = timedelta(seconds=1)
    if (
        abs(_as_utc(extracted.start) - _as_utc(target.start)) > tolerance
        or abs(_as_utc(extracted.end) - _as_utc(target.end)) > tolerance
    ):
        return RangeValidation(
            status="failed",
            requested_start=target.start,
            requested_end=target.end,
            extracted_start=extracted.start,
            extracted_end=extracted.end,
            error=(
                "Rewritten request range does not match target "
                f"{_iso(target.start)} -> {_iso(target.end)}."
            ),
        )
    return RangeValidation(
        status="passed",
        requested_start=target.start,
        requested_end=target.end,
        extracted_start=extracted.start,
        extracted_end=extracted.end,
    )


def extract_query_time_range(payload: dict[str, Any]) -> QueryTimeRange | None:
    candidates: list[tuple[datetime, datetime, str | None, str | None]] = []
    _extract(payload, candidates)
    if not candidates:
        return None
    start, end, timezone, label = candidates[0]
    return QueryTimeRange(start=start, end=end, timezone=timezone, label=label)


def _rewrite(value: Any, target: IngestionChunk) -> bool:
    changed = False
    if isinstance(value, dict):
        namespace = value.get("predicateFnNamespace")
        path = _predicate_path(value)
        if _is_quantum_ts_predicate(namespace, path):
            namespace_list = cast(list[Any], namespace)
            arguments = value.get("arguments")
            if isinstance(arguments, list) and arguments:
                value_index = 1 if isinstance(arguments[0], dict) and len(arguments) > 1 else 0
                if namespace_list[-1] == "gte":
                    arguments[value_index] = _format_like(arguments[value_index], target.start)
                elif namespace_list[-1] == "lt":
                    arguments[value_index] = _format_like(arguments[value_index], target.end)
                changed = True
        for key, child in list(value.items()):
            if key == "ts" and _is_window(child):
                value[key] = [
                    _format_like(child[0], target.start),
                    _format_like(child[1], target.end),
                ]
                changed = True
            elif key in {"baseTs", "startTs"}:
                value[key] = _format_like(child, target.start)
                changed = True
            elif key in {"endTs"}:
                value[key] = _format_like(child, target.end)
                changed = True
            elif key == "period" and isinstance(child, str | int | float):
                continue
            elif key == "periodCount" and isinstance(child, str | int | float):
                value[key] = max(1, (target.end.date() - target.start.date()).days + 1)
                changed = True
            elif key == "dimensionFills":
                if _rewrite_dimension_fills(child, target):
                    changed = True
            elif _rewrite(child, target):
                changed = True
    elif isinstance(value, list):
        for child in value:
            if _rewrite(child, target):
                changed = True
    return changed


def _extract(
    value: Any, candidates: list[tuple[datetime, datetime, str | None, str | None]]
) -> None:
    if isinstance(value, dict):
        ts = value.get("ts")
        if _is_window(ts):
            window = cast(list[Any], ts)
            start = _parse_time(window[0])
            end = _parse_time(window[1])
            if start and end:
                candidates.append(
                    (start, end, _text(value.get("timezone")), _text(value.get("period")))
                )
        base = _parse_time(value.get("baseTs") or value.get("startTs"))
        end_ts = _parse_time(value.get("endTs"))
        if base and end_ts:
            candidates.append((base, end_ts, _timezone_from_offset(value.get("utcOffset")), None))
        namespace = value.get("predicateFnNamespace")
        path = _predicate_path(value)
        if _is_quantum_ts_predicate(namespace, path):
            arguments = value.get("arguments")
            if isinstance(arguments, list) and arguments:
                value_index = 1 if isinstance(arguments[0], dict) and len(arguments) > 1 else 0
                point = _parse_time(arguments[value_index])
                if point:
                    candidates.append((point, point, None, None))
        dimension_fills = value.get("dimensionFills")
        if dimension_fills is not None:
            _extract_dimension_fills(dimension_fills, candidates)
        for child in value.values():
            _extract(child, candidates)
    elif isinstance(value, list):
        for child in value:
            _extract(child, candidates)

    _merge_predicates(candidates)


def _merge_predicates(candidates: list[tuple[datetime, datetime, str | None, str | None]]) -> None:
    if len(candidates) < 2:
        return
    starts = [start for start, end, _, _ in candidates if start == end]
    if len(starts) >= 2:
        candidates.insert(0, (min(starts), max(starts), None, None))


def _is_quantum_ts_predicate(namespace: Any, path: Any) -> bool:
    return (
        isinstance(namespace, list)
        and namespace[-1:] in (["gte"], ["lt"])
        and isinstance(path, list)
        and path[-2:] in (["session", "ts"], ["hit", "ts"])
    )


def _predicate_path(value: dict[str, Any]) -> Any:
    path = value.get("path")
    if path is not None:
        return path
    arguments = value.get("arguments")
    if isinstance(arguments, list) and arguments:
        first = arguments[0]
        if isinstance(first, dict):
            return first.get("path")
    return None


def _is_window(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 2


def _rewrite_dimension_fills(value: Any, target: IngestionChunk) -> bool:
    changed = False
    if isinstance(value, dict):
        arguments = value.get("arguments")
        if _is_dimension_fill_window(arguments):
            window = cast(list[Any], arguments)
            window[0] = _format_like(window[0], target.start)
            window[1] = _format_like(window[1], target.end)
            changed = True
        for child in value.values():
            if _rewrite_dimension_fills(child, target):
                changed = True
    elif isinstance(value, list):
        for child in value:
            if _rewrite_dimension_fills(child, target):
                changed = True
    return changed


def _extract_dimension_fills(
    value: Any,
    candidates: list[tuple[datetime, datetime, str | None, str | None]],
) -> None:
    if isinstance(value, dict):
        arguments = value.get("arguments")
        if _is_dimension_fill_window(arguments):
            window = cast(list[Any], arguments)
            start = _parse_time(window[0])
            end = _parse_time(window[1])
            if start and end:
                timezone = _timezone_from_offset(window[3]) if len(window) > 3 else None
                candidates.append((start, end, timezone, None))
        for child in value.values():
            _extract_dimension_fills(child, candidates)
    elif isinstance(value, list):
        for child in value:
            _extract_dimension_fills(child, candidates)


def _is_dimension_fill_window(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= 3
        and _parse_time(value[0]) is not None
        and _parse_time(value[1]) is not None
        and isinstance(value[2], int | float | str)
    )


def _format_like(template: Any, value: datetime) -> str | int | float:
    utc_value = _as_utc(value)
    if isinstance(template, int):
        return int(_epoch_like(template, utc_value))
    if isinstance(template, float):
        return float(_epoch_like(template, utc_value))
    if isinstance(template, str) and template.isdigit():
        return str(int(_epoch_like(int(template), utc_value)))
    return utc_value.isoformat().replace("+00:00", "Z")


def _epoch_like(template: int | float, value: datetime) -> int:
    timestamp = value.timestamp()
    return round(timestamp * 1000) if abs(template) > 10_000_000_000 else round(timestamp)


def _parse_time(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _as_utc(value)
    if isinstance(value, int | float):
        timestamp = value / 1000 if abs(value) > 10_000_000_000 else value
        return datetime.fromtimestamp(timestamp, UTC)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.isdigit():
            return _parse_time(int(raw))
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            return None
    return None


def _timezone_from_offset(value: Any) -> str | None:
    try:
        offset = int(value)
    except (TypeError, ValueError):
        return None
    if offset == -21600:
        return "CST"
    return f"UTC{offset // 3600:+03d}:00"


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")
