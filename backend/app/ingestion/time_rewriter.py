from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
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


def rewrite_query_time_range(payload: dict[str, Any], target: IngestionChunk) -> RewriteResult:
    rewritten = deepcopy(payload)
    changed = _rewrite(rewritten, target)
    return RewriteResult(
        payload=rewritten,
        changed=changed,
        range=QueryTimeRange(
            start=target.start, end=target.end, timezone="CST", label=target.label
        ),
    )


def extract_query_time_range(payload: dict[str, Any]) -> QueryTimeRange | None:
    candidates: list[tuple[datetime, datetime, str | None, str | None]] = []
    _extract(payload, candidates)
    _merge_predicates(candidates)
    if not candidates:
        return None
    start, end, timezone, label = candidates[0]
    return QueryTimeRange(start=start, end=end, timezone=timezone, label=label)


def _rewrite(value: Any, target: IngestionChunk) -> bool:
    changed = False
    if isinstance(value, dict):
        namespace = value.get("predicateFnNamespace")
        path = _predicate_path(value)
        if _is_session_ts_predicate(namespace, path):
            namespace_list = cast(list[Any], namespace)
            arguments = value.get("arguments")
            argument_index = _predicate_value_index(arguments)
            if isinstance(arguments, list) and argument_index is not None:
                if namespace_list[-1] == "gte":
                    arguments[argument_index] = _format_like(
                        arguments[argument_index], target.start
                    )
                elif namespace_list[-1] == "lt":
                    arguments[argument_index] = _format_like(arguments[argument_index], target.end)
                changed = True
        namespace = value.get("namespace")
        arguments = value.get("arguments")
        if (
            isinstance(namespace, list)
            and namespace[-1:] == ["ts"]
            and isinstance(arguments, list)
            and len(arguments) >= 2
        ):
            arguments[0] = _format_like(arguments[0], target.start)
            arguments[1] = _format_like(arguments[1], target.end)
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
            elif key == "historicalRequest" and isinstance(child, dict):
                if "period" in child:
                    child["period"] = "custom"
                    changed = True
                if "periodCount" in child:
                    child["periodCount"] = 1
                    changed = True
            elif key in {"period", "periodCount"} and isinstance(child, str | int | float):
                continue
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
        if _is_session_ts_predicate(namespace, path):
            arguments = value.get("arguments")
            argument_index = _predicate_value_index(arguments)
            if isinstance(arguments, list) and argument_index is not None:
                point = _parse_time(arguments[argument_index])
                if point:
                    candidates.append((point, point, None, None))
        namespace = value.get("namespace")
        arguments = value.get("arguments")
        if (
            isinstance(namespace, list)
            and namespace[-1:] == ["ts"]
            and isinstance(arguments, list)
            and len(arguments) >= 2
        ):
            start = _parse_time(arguments[0])
            end = _parse_time(arguments[1])
            if start and end:
                candidates.append(
                    (
                        start,
                        end,
                        _timezone_from_offset(arguments[3]) if len(arguments) > 3 else None,
                        None,
                    )
                )
        for child in value.values():
            _extract(child, candidates)
    elif isinstance(value, list):
        for child in value:
            _extract(child, candidates)


def _merge_predicates(candidates: list[tuple[datetime, datetime, str | None, str | None]]) -> None:
    if len(candidates) < 2:
        return
    starts = [start for start, end, _, _ in candidates if start == end]
    if len(starts) >= 2:
        candidates.insert(0, (min(starts), max(starts), None, None))


def _is_session_ts_predicate(namespace: Any, path: Any) -> bool:
    return (
        isinstance(namespace, list)
        and namespace[-1:] in (["gte"], ["lt"])
        and isinstance(path, list)
        and path[-2:] == ["session", "ts"]
    )


def _predicate_path(value: dict[str, Any]) -> Any:
    path = value.get("path")
    if isinstance(path, list):
        return path
    arguments = value.get("arguments")
    if isinstance(arguments, list) and arguments:
        first = arguments[0]
        if isinstance(first, dict):
            return first.get("path")
    return None


def _predicate_value_index(arguments: Any) -> int | None:
    if not isinstance(arguments, list) or not arguments:
        return None
    first = arguments[0]
    if isinstance(first, dict) and isinstance(first.get("path"), list):
        return 1 if len(arguments) > 1 else None
    return 0


def _is_window(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 2


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
