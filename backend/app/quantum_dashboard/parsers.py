from __future__ import annotations

from typing import Any

from backend.app.analytics.normalizer import (
    canonicalize_key,
    extract_response_rows,
    flatten_row,
    parse_json_object,
)
from backend.app.quantum_dashboard.catalog import (
    ERRORS_APP_COMPARISON,
    ERRORS_APP_PERCENTAGE,
    ERRORS_EVOLUTION,
    ERRORS_TOP_ERRORS,
    ROLE_SPECS,
    SUMMARY_AVG_SESSION_DURATION,
    SUMMARY_CONVERTED_SESSIONS,
    SUMMARY_PAGE_VIEWS,
    SUMMARY_SESSIONS,
)
from backend.app.quantum_dashboard.chart_axes import (
    format_tick_label,
    readable_x_ticks,
    readable_y_ticks,
)
from backend.app.quantum_dashboard.models import ParserResult, VisualRole

METRIC_ALIASES: dict[VisualRole, tuple[str, ...]] = {
    SUMMARY_PAGE_VIEWS: ("page_views", "pageviews", "page view count", "paginas vistas"),
    SUMMARY_SESSIONS: ("sessions", "session_count", "sesiones"),
    SUMMARY_CONVERTED_SESSIONS: (
        "converted_sessions",
        "sessions_with_conversion",
        "general conversiones",
        "general - conversiones",
        "conversiones",
        "conversions",
    ),
    SUMMARY_AVG_SESSION_DURATION: (
        "avg_session_duration",
        "average_session_duration",
        "avg_session_time",
        "tiempo medio de sesion",
    ),
    ERRORS_EVOLUTION: (
        "error_session_percent",
        "error_session_percentage",
        "percent_sessions_with_error",
        "% sesiones con error",
    ),
    ERRORS_TOP_ERRORS: ("sessions_with_error", "error_sessions", "sesiones con error"),
    ERRORS_APP_COMPARISON: ("sessions_with_error", "error_sessions", "sesiones con error"),
    ERRORS_APP_PERCENTAGE: (
        "error_session_percent",
        "error_session_percentage",
        "% sesiones con error",
    ),
}

SUMMARY_TABLE_ALIASES = {
    "name": ("name", "app_name", "app name"),
    "app_name": ("app_name", "app name", "application name"),
    "operating_system": ("operating_system", "operating system", "os", "os_name"),
    "page_views": ("page_views", "page views", "paginas vistas"),
    "sessions": ("sessions", "sesiones"),
    "conversions": ("conversions", "conversiones", "general conversiones"),
    "page_views_delta_percent": ("page_views_delta_percent", "page views delta percent"),
    "conversions_delta_percent": ("conversions_delta_percent", "conversions delta percent"),
}

ERROR_TABLE_ALIASES = {
    "name": ("name", "error_name", "error name", "app_name", "app name"),
    "error_name": ("error_name", "error name", "name"),
    "app_name": ("app_name", "app name", "name"),
    "sessions": ("sessions", "sesiones"),
    "error_sessions": ("error_sessions", "sessions_with_error", "sesiones con error"),
    "sessions_with_error": ("sessions_with_error", "error_sessions", "sesiones con error"),
    "error_session_percent": (
        "error_session_percent",
        "error_session_percentage",
        "% sesiones con error",
    ),
}


def parse_card(call: dict[str, Any], role: VisualRole) -> ParserResult:
    response_json = parse_json_object(call.get("response_json"))
    if not response_json:
        return _error(role, "empty_response", "Quantum response_json is empty or not JSON.")
    strategy = ROLE_SPECS[role].parse_strategy
    if strategy in {
        "timeseries_metric_card_v1",
        "single_metric_breakdown_card_v1",
        "historical_comparison_card_v1",
    }:
        return _parse_metric_widget(call, role, response_json)
    if strategy == "dimension_table_card_v1":
        return _parse_summary_table(role, response_json)
    if strategy == "top_errors_table_card_v1":
        return _parse_top_errors(role, response_json)
    if strategy == "percentage_table_card_v1":
        return _parse_error_percentage(role, response_json)
    if strategy == "donut_distribution_card_v1":
        return _parse_donut(role, response_json)
    return _error(role, "missing_strategy", f"No parser strategy registered for {strategy}.")


def _parse_metric_widget(
    call: dict[str, Any],
    role: VisualRole,
    response_json: dict[str, Any],
) -> ParserResult:
    spec = ROLE_SPECS[role]
    metric_aliases = METRIC_ALIASES[role]
    rows = _rows(response_json)
    value = _number_from_object(
        response_json,
        (*metric_aliases, "visible_value", "main_value", "total", "value"),
    )
    if value is None:
        row_values = [_number_from_row(row, metric_aliases) or _metric_at(row, 0) for row in rows]
        values = [item for item in row_values if item is not None]
        if values:
            value = _aggregate_values(values, average=spec.unit in {"seconds", "percent"})
    timeseries = _timeseries(response_json, metric_aliases)
    if value is None and timeseries:
        values = [point["value"] for point in timeseries]
        value = _aggregate_values(values, average=spec.unit in {"seconds", "percent"})
    if value is None:
        result_values = _values_from_results(response_json)
        if result_values:
            value = _aggregate_values(
                result_values,
                average=spec.unit in {"seconds", "percent"},
            )
    if value is None:
        return _error(role, "metric_not_found", f"No value found for role {role}.")
    if spec.unit == "percent":
        value = _as_percent(value) or value

    widget = {
        "id": spec.local_id,
        "role": role,
        "title": spec.title,
        "value": value,
        "unit": spec.unit or "count",
        "breakdown": _breakdowns(response_json, rows, metric_aliases),
        "timeseries": timeseries,
        "comparison": _comparison(response_json),
        "chart_payload": _line_chart_payload(
            response_json=response_json,
            role=role,
            title=spec.title,
            unit=spec.unit or "count",
            points=timeseries,
        ),
        "missing_source_field": None,
    }
    return ParserResult(role=role, status="ok", data={"widget": widget})


def _parse_summary_table(role: VisualRole, response_json: dict[str, Any]) -> ParserResult:
    rows = []
    for row in _rows(response_json):
        flat = flatten_row(row)
        dimensions = row.get("dimensions") if isinstance(row, dict) else None
        parsed = {
            "name": _string_from_row(flat, SUMMARY_TABLE_ALIASES["name"])
            or _dimension_at(row, 0)
            or "Null",
            "app_name": _string_from_row(flat, SUMMARY_TABLE_ALIASES["app_name"]),
            "operating_system": _string_from_row(flat, SUMMARY_TABLE_ALIASES["operating_system"]),
            "page_views": _number_from_row(flat, SUMMARY_TABLE_ALIASES["page_views"]),
            "sessions": _number_from_row(flat, SUMMARY_TABLE_ALIASES["sessions"]),
            "conversions": _number_from_row(flat, SUMMARY_TABLE_ALIASES["conversions"]),
            "page_views_delta_percent": _number_from_row(
                flat, SUMMARY_TABLE_ALIASES["page_views_delta_percent"]
            ),
            "sessions_delta_percent": _number_from_row(
                flat, ("sessions_delta_percent", "sessions delta percent")
            ),
            "conversions_delta_percent": _number_from_row(
                flat, SUMMARY_TABLE_ALIASES["conversions_delta_percent"]
            ),
        }
        for key in (
            "row_id",
            "parent_row_id",
            "depth",
            "is_expandable",
            "is_expanded_default",
        ):
            if key in flat:
                parsed[key] = flat[key]
        if isinstance(dimensions, list) and len(dimensions) > 1:
            parsed["operating_system"] = str(dimensions[1])
        if parsed["sessions"] is None and parsed["page_views"] is None:
            parsed["sessions"] = _metric_at(row, 0)
            parsed["conversions"] = _metric_at(row, 1)
            parsed["page_views"] = _metric_at(row, 2)
        if parsed["app_name"] is None:
            parsed["app_name"] = parsed["name"]
        if any(parsed[key] is not None for key in ("page_views", "sessions", "conversions")):
            rows.append(parsed)
    if not rows:
        return _error(role, "row_shape_unknown", "Summary detail table has no parseable rows.")
    rows = _expandable_summary_rows(rows)
    return ParserResult(
        role=role,
        status="ok",
        data={
            "columns": [
                "name",
                "app_name",
                "operating_system",
                "page_views",
                "sessions",
                "conversions",
            ],
            "rows": rows,
        },
    )


def _parse_top_errors(role: VisualRole, response_json: dict[str, Any]) -> ParserResult:
    rows = []
    for row in _rows(response_json):
        flat = flatten_row(row)
        parsed = {
            "name": _string_from_row(flat, ERROR_TABLE_ALIASES["name"])
            or _dimension_at(row, 0)
            or "Null",
            "error_name": _string_from_row(flat, ERROR_TABLE_ALIASES["error_name"]),
            "error_sessions": _number_from_row(flat, ERROR_TABLE_ALIASES["error_sessions"]),
            "sessions_with_error": _number_from_row(
                flat, ERROR_TABLE_ALIASES["sessions_with_error"]
            ),
            "error_session_percent": _number_from_row(
                flat, ERROR_TABLE_ALIASES["error_session_percent"]
            ),
            "error_session_percent_delta": _number_from_row(
                flat,
                (
                    "error_session_percent_delta",
                    "error_session_percent_delta_percent",
                    "error session percent delta",
                ),
            ),
        }
        if parsed["error_sessions"] is None:
            parsed["error_session_percent"] = _as_percent(_metric_at(row, 0))
            parsed["error_sessions"] = _metric_at(row, 1)
        if parsed["error_name"] is None:
            parsed["error_name"] = parsed["name"]
        if parsed["error_sessions"] is None:
            parsed["error_sessions"] = parsed["sessions_with_error"]
        if parsed["sessions_with_error"] is None:
            parsed["sessions_with_error"] = parsed["error_sessions"]
        if parsed["error_sessions"] is not None or parsed["error_session_percent"] is not None:
            rows.append(parsed)
    rows.sort(key=lambda item: _sort_number(item.get("error_sessions")), reverse=True)
    if not rows:
        return _error(role, "row_shape_unknown", "Top errors table has no parseable rows.")
    return ParserResult(
        role=role,
        status="ok",
        data={
            "columns": ["name", "error_sessions", "error_session_percent"],
            "rows": rows[:20],
        },
    )


def _parse_error_percentage(role: VisualRole, response_json: dict[str, Any]) -> ParserResult:
    rows = []
    for row in _rows(response_json):
        flat = flatten_row(row)
        parsed = {
            "name": _string_from_row(flat, ERROR_TABLE_ALIASES["name"])
            or _dimension_at(row, 0)
            or "Null",
            "app_name": _string_from_row(flat, ERROR_TABLE_ALIASES["app_name"]),
            "sessions": _number_from_row(flat, ERROR_TABLE_ALIASES["sessions"]),
            "sessions_with_error": _number_from_row(
                flat, ERROR_TABLE_ALIASES["sessions_with_error"]
            ),
            "error_session_percent": _number_from_row(
                flat, ERROR_TABLE_ALIASES["error_session_percent"]
            ),
            "error_session_percent_delta": _number_from_row(
                flat,
                (
                    "error_session_percent_delta",
                    "error_session_percent_delta_percent",
                    "error session percent delta",
                ),
            ),
        }
        if parsed["error_session_percent"] is None:
            parsed["error_session_percent"] = _as_percent(_metric_at(row, 0))
        if parsed["sessions_with_error"] is None:
            parsed["sessions_with_error"] = _metric_at(row, 1)
        if parsed["app_name"] is None:
            parsed["app_name"] = parsed["name"]
        if parsed["error_session_percent"] is not None:
            rows.append(parsed)
    rows.sort(key=lambda item: _sort_number(item.get("error_session_percent")), reverse=True)
    if not rows:
        return _error(role, "row_shape_unknown", "Error percentage table has no parseable rows.")
    return ParserResult(
        role=role,
        status="ok",
        data={
            "columns": ["name", "sessions", "sessions_with_error", "error_session_percent"],
            "rows": rows,
        },
    )


def _parse_donut(role: VisualRole, response_json: dict[str, Any]) -> ParserResult:
    series = _series(response_json)
    if not series:
        for row in _rows(response_json):
            flat = flatten_row(row)
            name = (
                _string_from_row(flat, ERROR_TABLE_ALIASES["app_name"])
                or _string_from_row(flat, ERROR_TABLE_ALIASES["name"])
                or _dimension_at(row, 0)
            )
            value = _number_from_row(flat, ERROR_TABLE_ALIASES["sessions_with_error"])
            if value is None:
                value = _metric_at(row, 0)
            if name and value is not None:
                series.append({"name": name, "value": value, "percent": 0.0})
    total = _number_from_object(response_json, ("total", "visible_value"))
    if total is None:
        total = round(sum(point["value"] for point in series), 2) if series else None
    if total:
        for point in series:
            if not point.get("percent"):
                point["percent"] = round((point["value"] / total) * 100, 2)
    if not series:
        return _error(role, "row_shape_unknown", "Donut card has no parseable series.")
    widget = {
        "id": ROLE_SPECS[role].local_id,
        "role": role,
        "title": ROLE_SPECS[role].title,
        "chart_type": "donut",
        "total": total,
        "series": series,
        "chart_payload": _donut_chart_payload(series, role, ROLE_SPECS[role].title),
        "comparison": _comparison(response_json),
    }
    return ParserResult(role=role, status="ok", data={"widget": widget})


def _rows(response_json: dict[str, Any]) -> list[Any]:
    rows = response_json.get("rows")
    if isinstance(rows, list):
        return rows
    return extract_response_rows(response_json)


def _values_from_results(response_json: dict[str, Any]) -> list[float]:
    results = response_json.get("results")
    if not isinstance(results, list):
        return []
    values: list[float] = []
    for item in results:
        value = _result_metric_value(item, 0)
        if value is not None:
            values.append(value)
    return values


def _timeseries(response_json: dict[str, Any], aliases: tuple[str, ...]) -> list[dict[str, Any]]:
    candidates = response_json.get("timeseries") or response_json.get("series")
    if not isinstance(candidates, list):
        candidates = []
    points: list[dict[str, Any]] = []
    for point in candidates:
        if not isinstance(point, dict):
            continue
        flat = flatten_row(point)
        ts = _string_from_row(flat, ("ts", "timestamp", "date", "time", "x"))
        value = _number_from_row(flat, (*aliases, "value", "y"))
        if ts and value is not None:
            points.append({"ts": ts, "value": value})
    if points:
        return points
    points_by_row: list[dict[str, Any]] = []
    for row in _rows(response_json):
        flat = flatten_row(row)
        ts = _string_from_row(flat, ("ts", "timestamp", "date", "time")) or _dimension_at(row, 0)
        value = _number_from_row(flat, aliases)
        if value is None:
            value = _metric_at(row, 0)
        if ts and value is not None:
            points_by_row.append({"ts": ts, "value": value})
    if points_by_row:
        return points_by_row
    return _timeseries_from_results(response_json)


def _timeseries_from_results(response_json: dict[str, Any]) -> list[dict[str, Any]]:
    results = response_json.get("results")
    if not isinstance(results, list):
        return []
    points = []
    for item in results:
        if not isinstance(item, list) or len(item) < 2:
            continue
        dimensions = item[0]
        ts = dimensions[0] if isinstance(dimensions, list) and dimensions else None
        metrics = item[1]
        value = None
        if isinstance(metrics, list) and metrics:
            metric_value = metrics[0]
            if isinstance(metric_value, list):
                value = _to_number(metric_value[-1] if metric_value else None)
            else:
                value = _to_number(metric_value)
        if ts is not None and value is not None:
            points.append({"ts": str(ts), "value": value})
    return points


def _breakdowns(
    response_json: dict[str, Any],
    rows: list[Any],
    aliases: tuple[str, ...],
) -> list[dict[str, Any]]:
    candidates = response_json.get("breakdown") or response_json.get("breakdowns")
    if isinstance(candidates, list):
        parsed = []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            flat = flatten_row(item)
            label = _string_from_row(flat, ("label", "name", "device_type", "platform"))
            value = _number_from_row(flat, (*aliases, "value"))
            if label and value is not None:
                parsed.append({"label": _display_bucket(label), "value": value})
        if parsed:
            return parsed

    buckets: dict[str, float] = {}
    for row in rows:
        flat = flatten_row(row)
        label = _string_from_row(flat, ("device_type", "device", "platform", "application_type"))
        value = _number_from_row(flat, aliases)
        if label and value is not None:
            display = _display_bucket(label)
            buckets[display] = buckets.get(display, 0.0) + value
    return [{"label": key, "value": round(value, 2)} for key, value in buckets.items()]


def _series(response_json: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = response_json.get("series") or response_json.get("breakdown")
    if not isinstance(candidates, list):
        return []
    series = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        flat = flatten_row(item)
        name = _string_from_row(flat, ("name", "label", "app_name", "app name"))
        value = _number_from_row(flat, ("value", "sessions_with_error", "error_sessions"))
        percent = _number_from_row(flat, ("percent", "percentage", "error_session_percent")) or 0.0
        if name and value is not None:
            series.append({"name": name, "value": value, "percent": percent})
    return series


def _comparison(response_json: dict[str, Any]) -> dict[str, Any] | None:
    comparison = response_json.get("comparison")
    if isinstance(comparison, dict):
        flat = flatten_row(comparison)
        delta = _number_from_row(flat, ("delta_percent", "delta", "percent"))
        return {"label": str(comparison.get("label") or "Historical Range"), "delta_percent": delta}
    delta = _number_from_object(response_json, ("delta_percent", "historical_delta_percent"))
    if delta is None:
        return None
    return {"label": "Historical Range", "delta_percent": delta}


def _number_from_object(value: dict[str, Any], aliases: tuple[str, ...]) -> float | None:
    return _number_from_row(flatten_row(value), aliases)


def _dimension_at(row: Any, index: int) -> str | None:
    if not isinstance(row, dict):
        return None
    dimensions = row.get("dimensions")
    if not isinstance(dimensions, list) or len(dimensions) <= index:
        return None
    value = dimensions[index]
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _metric_at(row: Any, index: int) -> float | None:
    if not isinstance(row, dict):
        return None
    metrics = row.get("metrics")
    if not isinstance(metrics, list) or len(metrics) <= index:
        return None
    return _to_number(metrics[index])


def _result_metric_value(item: Any, metric_index: int) -> float | None:
    if not isinstance(item, list) or len(item) < 2:
        return None
    metrics = item[1]
    if not isinstance(metrics, list) or len(metrics) <= metric_index:
        return None
    metric_value = metrics[metric_index]
    if isinstance(metric_value, list):
        if not metric_value:
            return None
        return _to_number(metric_value[0])
    return _to_number(metric_value)


def _number_from_row(row: dict[str, Any], aliases: tuple[str, ...]) -> float | None:
    alias_keys = {canonicalize_key(alias) for alias in aliases}
    for key, value in row.items():
        if canonicalize_key(key) in alias_keys:
            parsed = _to_number(value)
            if parsed is not None:
                return parsed
    return None


def _string_from_row(row: dict[str, Any], aliases: tuple[str, ...]) -> str | None:
    alias_keys = {canonicalize_key(alias) for alias in aliases}
    for key, value in row.items():
        if canonicalize_key(key) in alias_keys and value is not None:
            text = str(value).strip()
            if text:
                return text
    return None


def _to_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    clean = value.strip().replace("%", "").replace(",", "")
    if not clean:
        return None
    try:
        return float(clean)
    except ValueError:
        return None


def _sort_number(value: object) -> float:
    parsed = _to_number(value)
    return parsed if parsed is not None else -1.0


def _as_percent(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value * 100, 2) if abs(value) <= 1 else value


def _aggregate_values(values: list[float], *, average: bool) -> float:
    if average:
        return round(sum(values) / len(values), 2)
    return round(sum(values), 2)


def _line_chart_payload(
    *,
    response_json: dict[str, Any],
    role: VisualRole,
    title: str,
    unit: str,
    points: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not points:
        return None
    y_values = [_to_number(point.get("value")) for point in points]
    numeric_values = [value for value in y_values if value is not None]
    if not numeric_values:
        return None
    y_min = min(0.0, min(numeric_values))
    y_max = max(numeric_values)
    if y_max == y_min:
        y_max = y_min + 1
    x_ticks = _axis_ticks_from_points(points)
    y_ticks = _numeric_ticks(y_min, y_max, unit)
    primary_points = [
        {
            "ts": str(point.get("ts")),
            "label": str(point.get("label") or _short_ts_label(point.get("ts"))),
            "value": _to_number(point.get("value")),
            "raw_value": _to_number(point.get("value")),
        }
        for point in points
        if point.get("ts") is not None and _to_number(point.get("value")) is not None
    ]
    desktop_points: list[dict[str, Any]] = []
    return {
        "chart_type": "line",
        "x_axis": {"ticks": x_ticks, "label": "Periodo"},
        "y_axis": {"min": y_min, "max": y_max, "unit": unit, "ticks": y_ticks, "label": title},
        "series": [
            {
                "id": f"{role}.mobile",
                "label": "Mobile",
                "kind": "line",
                "device": "mobile",
                "points": primary_points,
                "visible": True,
            },
            {
                "id": f"{role}.desktop",
                "label": "Desktop",
                "kind": "line",
                "device": "desktop",
                "points": desktop_points,
                "visible": True,
            },
        ],
        "bands": _bands(response_json),
        "legends": [
            {"id": "mobile", "label": "Mobile", "device": "mobile"},
            {"id": "desktop", "label": "Desktop", "device": "desktop"},
        ],
        "period_label": None,
        "granularity": _granularity(points),
        "timezone": _timezone(response_json),
    }


def _donut_chart_payload(
    series: list[dict[str, Any]],
    role: VisualRole,
    title: str,
) -> dict[str, Any]:
    points = [
        {
            "ts": None,
            "label": str(point.get("name") or "Null"),
            "value": _to_number(point.get("value")) or 0.0,
            "raw_value": _to_number(point.get("percent")) or 0.0,
        }
        for point in series
    ]
    return {
        "chart_type": "donut",
        "x_axis": {"ticks": [], "label": title},
        "y_axis": {"min": 0, "max": sum(point["value"] or 0 for point in points), "unit": "count"},
        "series": [
            {
                "id": f"{role}.segments",
                "label": title,
                "kind": "bar",
                "device": "unknown",
                "points": points,
                "visible": True,
            }
        ],
        "bands": [],
        "legends": [
            {"id": str(point.get("name") or index), "label": str(point.get("name") or "Null")}
            for index, point in enumerate(series)
        ],
        "period_label": None,
        "granularity": None,
        "timezone": _timezone({}),
    }


def _axis_ticks_from_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return readable_x_ticks(points, timezone="CST")


def _numeric_ticks(min_value: float, max_value: float, unit: str) -> list[dict[str, Any]]:
    return readable_y_ticks(min_value, max_value, unit)


def _format_tick(value: float, unit: str) -> str:
    if unit == "seconds":
        return f"{value:,.0f} sec"
    if unit == "percent":
        return f"{value:,.0f}%"
    return f"{value:,.0f}"


def _short_ts_label(value: Any) -> str:
    return format_tick_label(value, timezone="CST")


def _bands(response_json: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = response_json.get("bands") or response_json.get("annotations") or []
    if not isinstance(candidates, list):
        return []
    bands: list[dict[str, Any]] = []
    for index, item in enumerate(candidates):
        if not isinstance(item, dict):
            continue
        flat = flatten_row(item)
        bands.append(
            {
                "id": str(item.get("id") or f"band-{index}"),
                "label": _string_from_row(flat, ("label", "name")),
                "start_ts": _string_from_row(flat, ("start_ts", "start", "from")),
                "end_ts": _string_from_row(flat, ("end_ts", "end", "to")),
                "purpose": _string_from_row(flat, ("purpose", "type")),
            }
        )
    return bands


def _granularity(points: list[dict[str, Any]]) -> str | None:
    if len(points) < 2:
        return None
    return "captured"


def _timezone(response_json: dict[str, Any]) -> str:
    metadata = response_json.get("metadata")
    if isinstance(metadata, dict) and metadata.get("timezone"):
        return str(metadata["timezone"])
    return "CST"


def _expandable_summary_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if any(row.get("parent_row_id") is not None or row.get("depth") is not None for row in rows):
        return [_with_hierarchy_defaults(row) for row in rows]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        app_name = str(row.get("app_name") or row.get("name") or "Null")
        grouped.setdefault(app_name, []).append(row)
    output: list[dict[str, Any]] = []
    for app_index, (app_name, children) in enumerate(grouped.items()):
        parent_id = f"app:{app_name}"
        parent = {
            "row_id": parent_id,
            "parent_row_id": None,
            "depth": 0,
            "is_expandable": True,
            "is_expanded_default": app_index == 0,
            "name": app_name,
            "app_name": app_name,
            "operating_system": None,
            "page_views": round(sum(_to_number(row.get("page_views")) or 0 for row in children), 2),
            "sessions": round(sum(_to_number(row.get("sessions")) or 0 for row in children), 2),
            "conversions": round(
                sum(_to_number(row.get("conversions")) or 0 for row in children), 2
            ),
            "page_views_delta_percent": _first_number(children, "page_views_delta_percent"),
            "sessions_delta_percent": _first_number(children, "sessions_delta_percent"),
            "conversions_delta_percent": _first_number(children, "conversions_delta_percent"),
        }
        parent.update(_semantic_states(parent))
        output.append(parent)
        child_rows = [child for child in children if _is_operating_system_child(child, app_name)]
        for child_index, child in enumerate(child_rows):
            child_row = {
                **child,
                "row_id": f"{parent_id}:os:{child.get('operating_system') or child_index}",
                "parent_row_id": parent_id,
                "depth": 1,
                "is_expandable": False,
                "is_expanded_default": True,
                "name": child.get("operating_system") or child.get("name") or "Null",
            }
            child_row.update(_semantic_states(child_row))
            output.append(child_row)
    return output


def _with_hierarchy_defaults(row: dict[str, Any]) -> dict[str, Any]:
    depth = int(_to_number(row.get("depth")) or 0)
    normalized = {
        **row,
        "row_id": row.get("row_id") or f"row:{row.get('name') or row.get('app_name')}",
        "parent_row_id": row.get("parent_row_id"),
        "depth": depth,
        "is_expandable": bool(row.get("is_expandable")) if depth == 0 else False,
        "is_expanded_default": bool(row.get("is_expanded_default")),
    }
    normalized.update(_semantic_states(normalized))
    return normalized


def _is_operating_system_child(row: dict[str, Any], app_name: str) -> bool:
    operating_system = str(row.get("operating_system") or "").strip()
    if not operating_system or operating_system.casefold() == "null":
        return False
    return operating_system.casefold() != app_name.casefold()


def _first_number(rows: list[dict[str, Any]], key: str) -> float | None:
    for row in rows:
        value = _to_number(row.get(key))
        if value is not None:
            return value
    return None


def _semantic_states(row: dict[str, Any]) -> dict[str, str]:
    states = {}
    for metric in ("page_views", "sessions", "conversions"):
        delta = _to_number(row.get(f"{metric}_delta_percent"))
        if delta is None:
            states[f"{metric}_semantic_state"] = "neutral"
        elif delta >= 0:
            states[f"{metric}_semantic_state"] = "positive"
        else:
            states[f"{metric}_semantic_state"] = "negative"
    return states


def _display_bucket(label: str) -> str:
    normalized = canonicalize_key(label)
    if "desktop" in normalized:
        return "Desktop"
    if "mobile" in normalized or "phone" in normalized or "app" in normalized:
        return "Mobile"
    return label


def _error(role: VisualRole, code: str, message: str) -> ParserResult:
    return ParserResult(role=role, status="error", error_code=code, error_message=message)
