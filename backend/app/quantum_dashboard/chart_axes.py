from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.app.quantum_dashboard.periods import parse_datetime, zoneinfo_for

MAX_X_TICKS = 7


def readable_x_ticks(
    points: list[dict[str, Any]],
    *,
    timezone: str = "CST",
    preset: str | None = None,
    max_ticks: int = MAX_X_TICKS,
) -> list[dict[str, Any]]:
    if not points:
        return []
    selected = _sample_points(points, max_ticks=max_ticks)
    denominator = max(1, len(points) - 1)
    ticks: list[dict[str, Any]] = []
    for index, point in selected:
        raw = point.get("ts")
        if raw is None:
            continue
        parsed = parse_datetime(raw, timezone)
        if parsed is None and not _is_non_temporal_label(raw):
            continue
        label = format_tick_label(raw, timezone=timezone, preset=preset)
        if not label:
            continue
        ticks.append(
            {
                "value": str(raw),
                "label": label,
                "position": round(index / denominator, 4),
            }
        )
    return ticks


def format_tick_label(value: Any, *, timezone: str = "CST", preset: str | None = None) -> str:
    parsed = parse_datetime(value, timezone)
    if parsed is None:
        text = "" if value is None else str(value)
        return text[:12]
    local = parsed.astimezone(zoneinfo_for(timezone))
    if preset in {"last_7_days"}:
        return local.strftime("%b %d")
    if preset == "custom":
        return (
            local.strftime("%b %d") if _looks_like_day_boundary(local) else local.strftime("%H:%M")
        )
    return local.strftime("%H:%M")


def readable_y_ticks(min_value: float, max_value: float, unit: str) -> list[dict[str, Any]]:
    if max_value < min_value:
        min_value, max_value = max_value, min_value
    span = max(max_value - min_value, 1)
    return [
        {
            "value": round(min_value + span * ratio, 4),
            "label": format_y_tick(min_value + span * ratio, unit),
            "position": ratio,
        }
        for ratio in (0, 0.5, 1)
    ]


def format_y_tick(value: float, unit: str) -> str:
    if unit == "seconds":
        return f"{value:,.0f} sec"
    if unit == "percent":
        return f"{value:,.0f}%"
    return f"{value:,.0f}"


def _sample_points(
    points: list[dict[str, Any]], *, max_ticks: int
) -> list[tuple[int, dict[str, Any]]]:
    if len(points) <= max_ticks:
        return list(enumerate(points))
    step = (len(points) - 1) / (max_ticks - 1)
    indexes = sorted({round(step * index) for index in range(max_ticks)})
    return [(index, points[index]) for index in indexes]


def _looks_like_day_boundary(value: datetime) -> bool:
    return value.hour == 0 and value.minute == 0


def _is_non_temporal_label(value: Any) -> bool:
    text = str(value)
    return bool(text and not text.isdigit())
