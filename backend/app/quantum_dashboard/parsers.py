from __future__ import annotations

from datetime import UTC, datetime
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
    readable_x_ticks,
    readable_y_ticks,
)
from backend.app.quantum_dashboard.generic_roles import infer_generic_unit, is_generic_role
from backend.app.quantum_dashboard.models import ParserResult, VisualRole
from backend.app.quantum_dashboard.periods import parse_datetime, zoneinfo_for

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
    "page_views_delta_percent": (
        "page_views_delta_percent",
        "page views delta percent",
        "page views delta",
        "delta page views",
        "delta_page_views",
    ),
    "sessions_delta_percent": (
        "sessions_delta_percent",
        "sessions delta percent",
        "sessions delta",
        "delta sessions",
        "delta_sessions",
    ),
    "conversions_delta_percent": (
        "conversions_delta_percent",
        "conversions delta percent",
        "conversions delta",
        "delta conversions",
        "delta_conversiones",
    ),
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
    if is_generic_role(role):
        return _parse_generic_card(call, role, response_json)
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


def _parse_generic_card(
    call: dict[str, Any],
    role: VisualRole,
    response_json: dict[str, Any],
) -> ParserResult:
    card_type = str(call.get("card_type") or call.get("widget_type") or "").upper()
    if card_type == "TABLE":
        return _parse_generic_table(call, role, response_json)
    if card_type == "DONUT":
        return _parse_generic_donut(call, role, response_json)
    return _parse_generic_metric(call, role, response_json)


def _parse_generic_metric(
    call: dict[str, Any],
    role: VisualRole,
    response_json: dict[str, Any],
) -> ParserResult:
    title = _generic_title(call, role)
    rows = _rows(response_json)
    value = _number_from_object(
        response_json,
        ("visible_value", "main_value", "total", "value", "count", "sessions"),
    )
    if value is None:
        values = _generic_row_metric_values(rows)
        if values:
            unit_hint = infer_generic_unit(title, values[0])
            value = _aggregate_values(values, average=unit_hint == "percent")
    timeseries = _generic_timeseries(response_json)
    if value is None and timeseries:
        unit_hint = infer_generic_unit(title, timeseries[0].get("value"))
        value = _aggregate_values(
            [point["value"] for point in timeseries],
            average=unit_hint == "percent",
        )
    if value is None:
        result_values = _values_from_results(response_json)
        if result_values:
            unit_hint = infer_generic_unit(title, result_values[0])
            value = _aggregate_values(result_values, average=unit_hint == "percent")
    if value is None:
        return _error(role, "metric_not_found", f"No generic value found for role {role}.")
    unit = infer_generic_unit(title, value)
    if unit == "percent":
        value = _as_percent(value) or value
        for point in timeseries:
            parsed = _to_number(point.get("value"))
            if parsed is not None:
                point["value"] = _as_percent(parsed) or parsed
    widget = {
        "id": role,
        "role": role,
        "title": title,
        "value": value,
        "unit": unit,
        "chart_type": "line",
        "breakdown": [],
        "timeseries": timeseries,
        "comparison": _comparison(response_json),
        "chart_payload": _line_chart_payload(
            response_json=response_json,
            role=role,
            title=title,
            unit=unit,
            points=timeseries,
        ),
        "missing_source_field": None,
    }
    return ParserResult(role=role, status="ok", data={"widget": widget})


def _parse_generic_table(
    call: dict[str, Any],
    role: VisualRole,
    response_json: dict[str, Any],
) -> ParserResult:
    parsed_rows: list[dict[str, Any]] = []
    for index, row in enumerate(_rows(response_json)):
        parsed = _generic_table_row(row, index)
        if parsed:
            parsed_rows.append(parsed)
    columns = _generic_table_columns(response_json, parsed_rows)
    widget = {
        "id": role,
        "role": role,
        "title": _generic_title(call, role),
        "value": len(parsed_rows),
        "unit": "count",
        "chart_type": "table",
        "breakdown": [],
        "timeseries": [],
        "table_columns": columns,
        "table_rows": parsed_rows,
        "comparison": _comparison(response_json),
    }
    return ParserResult(
        role=role,
        status="ok",
        data={"columns": columns, "rows": parsed_rows, "widget": widget},
    )


def _parse_generic_donut(
    call: dict[str, Any],
    role: VisualRole,
    response_json: dict[str, Any],
) -> ParserResult:
    series = _series(response_json)
    if not series:
        for row in _rows(response_json):
            label = _dimension_label(row, 0)
            value = _first_metric_value(row)
            if value is not None:
                series.append({"name": label, "value": value, "percent": 0.0})
    if not series:
        return _error(role, "row_shape_unknown", "Generic donut has no parseable series.")
    series = _group_web_donut_series(series)
    total = _number_from_object(response_json, ("total", "visible_value")) or round(
        sum(float(point.get("value") or 0) for point in series),
        2,
    )
    title = _generic_title(call, role)
    widget = {
        "id": role,
        "role": role,
        "title": title,
        "chart_type": "donut",
        "total": total,
        "value": total,
        "unit": "count",
        "series": series,
        "chart_payload": _donut_chart_payload(series, role, title),
        "comparison": _comparison(response_json),
    }
    return ParserResult(role=role, status="ok", data={"widget": widget})


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
                flat, SUMMARY_TABLE_ALIASES["sessions_delta_percent"]
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
    rows = _summary_rows_with_real_hierarchy(rows)
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
                or _dimension_label(row, 0)
            )
            value = _number_from_row(flat, ERROR_TABLE_ALIASES["sessions_with_error"])
            if value is None:
                value = _metric_at(row, 0)
            if value is not None:
                series.append({"name": name, "value": value, "percent": 0.0})
    series = _group_web_donut_series(series)
    total = _number_from_object(response_json, ("total", "visible_value"))
    percentage_total = round(sum(point["value"] for point in series), 2) if series else None
    if total is None:
        total = percentage_total
    if percentage_total:
        for point in series:
            if not point.get("percent"):
                point["percent"] = round((point["value"] / percentage_total) * 100, 2)
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


def _generic_title(call: dict[str, Any], role: str) -> str:
    return str(call.get("card_title") or call.get("title") or role)


def _generic_row_metric_values(rows: list[Any]) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = _first_metric_value(row)
        if value is not None:
            values.append(value)
    return values


def _first_metric_value(row: Any) -> float | None:
    if isinstance(row, dict):
        metrics = row.get("metrics")
        if isinstance(metrics, list):
            for metric in metrics:
                value = _to_number(metric[-1] if isinstance(metric, list) and metric else metric)
                if value is not None:
                    return value
        value = _to_number(metrics)
        if value is not None:
            return value
        flat = flatten_row(row)
        for key in ("value", "count", "sessions", "metric", "metrics"):
            value = _number_from_row(flat, (key,))
            if value is not None:
                return value
    return None


def _generic_timeseries(response_json: dict[str, Any]) -> list[dict[str, Any]]:
    points = _timeseries(response_json, ("value", "count", "sessions", "metric", "metrics"))
    if points:
        return points
    parsed: list[dict[str, Any]] = []
    for row in _rows(response_json):
        if not isinstance(row, dict):
            continue
        ts = _dimension_at(row, 0)
        value = _first_metric_value(row)
        if ts and value is not None:
            parsed.append({"ts": ts, "value": value})
    return parsed


def _generic_table_row(row: Any, index: int) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    flat = flatten_row(row)
    parsed: dict[str, Any] = {"row_index": index}
    dimensions = row.get("dimensions")
    if isinstance(dimensions, list):
        for dimension_index, value in enumerate(dimensions, start=1):
            parsed[f"dimension_{dimension_index}"] = value
        if dimensions:
            parsed["name"] = "Null" if dimensions[0] is None else str(dimensions[0])
    elif dimensions is not None:
        parsed["dimension_1"] = dimensions
        parsed["name"] = "Null" if dimensions is None else str(dimensions)
    metrics = row.get("metrics")
    if isinstance(metrics, list):
        for metric_index, value in enumerate(metrics, start=1):
            parsed[f"metric_{metric_index}"] = _to_number(
                value[-1] if isinstance(value, list) and value else value
            )
    elif metrics is not None:
        parsed["metric_1"] = _to_number(metrics)
    for key, value in flat.items():
        if key not in parsed and key not in {"dimensions", "metrics"}:
            parsed[canonicalize_key(key)] = value
    if "name" not in parsed:
        parsed["name"] = _string_from_row(flat, ("name", "error name", "app name")) or "Null"
    return parsed


def _generic_table_columns(
    response_json: dict[str, Any],
    rows: list[dict[str, Any]],
) -> list[str]:
    response_columns = response_json.get("columns") or response_json.get("columnNames")
    columns: list[str] = []
    if isinstance(response_columns, list):
        for column in response_columns:
            if isinstance(column, str):
                columns.append(canonicalize_key(column))
            elif isinstance(column, dict):
                value = column.get("key") or column.get("name") or column.get("label")
                if value:
                    columns.append(canonicalize_key(str(value)))
    if not columns and rows:
        preferred = ["name"]
        metric_keys = sorted({key for row in rows for key in row if key.startswith("metric_")})
        dimension_keys = sorted(
            {key for row in rows for key in row if key.startswith("dimension_")}
        )
        columns = [key for key in [*preferred, *dimension_keys, *metric_keys] if key in rows[0]]
    if not rows:
        return columns
    extras = [key for key in rows[0] if key not in columns and key != "row_index"]
    return [*columns, *extras]


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


def _group_web_donut_series(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(series) <= 5:
        return series
    null_items = [item for item in series if str(item.get("name") or "").strip() == "Null"]
    named_items = [item for item in series if str(item.get("name") or "").strip() != "Null"]
    keep = named_items[:3]
    other_value = round(sum(float(item.get("value") or 0) for item in named_items[3:]), 2)
    grouped: list[dict[str, Any]] = []
    if null_items:
        grouped.append(
            {"name": "Null", "value": round(sum(item["value"] for item in null_items), 2)}
        )
    if other_value:
        grouped.append({"name": "Other", "value": other_value})
    grouped.extend(keep)
    return grouped


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


def _dimension_label(row: Any, index: int) -> str:
    if not isinstance(row, dict):
        return "Null"
    dimensions = row.get("dimensions")
    if not isinstance(dimensions, list) or len(dimensions) <= index:
        return "Null"
    value = dimensions[index]
    if value is None:
        return "Null"
    text = str(value).strip()
    return text or "Null"


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
    return build_line_chart_payload_from_series(
        role=role,
        title=title,
        unit=unit,
        mobile_points=points,
        desktop_points=[],
        response_json=response_json,
    )


def build_line_chart_payload_from_series(
    *,
    role: VisualRole,
    title: str,
    unit: str,
    mobile_points: list[dict[str, Any]],
    desktop_points: list[dict[str, Any]],
    response_json: dict[str, Any] | None = None,
    aggregate_daily: bool = False,
    period_end: str | datetime | None = None,
    mobile_label: str = "Mobile",
    desktop_label: str = "Desktop",
) -> dict[str, Any] | None:
    point_builder = _visual_timeseries_points if aggregate_daily else _captured_timeseries_points
    parsed_period_end = parse_datetime(period_end, timezone="CST") if aggregate_daily else None
    mobile_visual_points = point_builder(mobile_points, unit, period_end=parsed_period_end)
    desktop_visual_points = point_builder(desktop_points, unit, period_end=parsed_period_end)
    all_points = [*mobile_visual_points, *desktop_visual_points]
    if not all_points:
        return None
    y_values = [_to_number(point.get("value")) for point in all_points]
    numeric_values = [value for value in y_values if value is not None]
    if not numeric_values:
        return None
    y_min = min(0.0, min(numeric_values))
    y_max = max(numeric_values)
    if y_max == y_min:
        y_max = y_min + 1
    x_ticks = _axis_ticks_from_points(
        mobile_visual_points if mobile_visual_points else desktop_visual_points,
        preset="last_7_days" if aggregate_daily else None,
    )
    y_ticks = _numeric_ticks(y_min, y_max, unit)
    return {
        "chart_type": "line",
        "x_axis": {"ticks": x_ticks, "label": "Periodo"},
        "y_axis": {"min": y_min, "max": y_max, "unit": unit, "ticks": y_ticks, "label": title},
        "series": [
            {
                "id": f"{role}.mobile",
                "label": mobile_label,
                "kind": "line",
                "device": "mobile",
                "points": mobile_visual_points,
                "visible": True,
            },
            {
                "id": f"{role}.desktop",
                "label": desktop_label,
                "kind": "line",
                "device": "desktop",
                "points": desktop_visual_points,
                "visible": bool(desktop_visual_points),
            },
        ],
        "bands": _bands(response_json or {}),
        "legends": [
            {"id": "mobile", "label": mobile_label, "device": "mobile"},
            {"id": "desktop", "label": desktop_label, "device": "desktop"},
        ],
        "period_label": None,
        "granularity": "daily" if aggregate_daily else "captured",
        "timezone": _timezone(response_json or {}),
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


def _axis_ticks_from_points(
    points: list[dict[str, Any]],
    *,
    preset: str | None,
) -> list[dict[str, Any]]:
    ticks = readable_x_ticks(points, timezone="CST", preset=preset)
    by_value = {str(point.get("ts")): str(point.get("label") or "") for point in points}
    return [
        {**tick, "label": by_value.get(str(tick.get("value"))) or tick.get("label")}
        for tick in ticks
    ]


def _numeric_ticks(min_value: float, max_value: float, unit: str) -> list[dict[str, Any]]:
    return readable_y_ticks(min_value, max_value, unit)


def _format_tick(value: float, unit: str) -> str:
    if unit == "seconds":
        return f"{value:,.0f} sec"
    if unit == "percent":
        return f"{value:,.0f}%"
    return f"{value:,.0f}"


def _short_ts_label(value: Any) -> str:
    parsed = parse_datetime(value, timezone="CST")
    if parsed is None:
        return "" if value is None else str(value)[:12]
    return parsed.astimezone(zoneinfo_for("CST")).strftime("%H:%M")


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


def _visual_timeseries_points(
    points: list[dict[str, Any]],
    unit: str,
    *,
    period_end: datetime | None = None,
) -> list[dict[str, Any]]:
    buckets: dict[str, list[float]] = {}
    bucket_ts: dict[str, str] = {}
    zone = zoneinfo_for("CST")
    partial_final_day = _partial_final_day(period_end, zone)
    for point in points:
        parsed = parse_datetime(point.get("ts"), timezone="CST")
        value = _to_number(point.get("value"))
        if parsed is None or value is None:
            continue
        if unit == "percent" and abs(value) <= 1:
            value *= 100
        local = parsed.astimezone(zone)
        key = local.date().isoformat()
        if key == partial_final_day:
            continue
        bucket_start = datetime.combine(local.date(), datetime.min.time(), tzinfo=zone)
        bucket_ts[key] = bucket_start.astimezone(UTC).isoformat().replace("+00:00", "Z")
        buckets.setdefault(key, []).append(value)
    visual_points: list[dict[str, Any]] = []
    for key in sorted(buckets):
        values = buckets[key]
        if not values:
            continue
        if unit in {"seconds", "percent"}:
            signal_values = [value for value in values if value != 0]
            value = sum(signal_values) / len(signal_values) if signal_values else 0
        else:
            value = sum(values)
        ts = bucket_ts[key]
        parsed_ts = parse_datetime(ts, timezone="CST")
        label = parsed_ts.astimezone(zoneinfo_for("CST")).strftime("%b %d") if parsed_ts else key
        visual_points.append(
            {
                "ts": ts,
                "label": label,
                "value": round(value, 2),
                "raw_value": round(value, 2),
            }
        )
    return visual_points


def _partial_final_day(period_end: datetime | None, zone: Any) -> str | None:
    if period_end is None:
        return None
    local_end = period_end.astimezone(zone)
    if local_end.hour == 23 and local_end.minute == 59:
        return None
    return local_end.date().isoformat()


def _captured_timeseries_points(
    points: list[dict[str, Any]],
    unit: str,
    *,
    period_end: datetime | None = None,
) -> list[dict[str, Any]]:
    del period_end
    parsed_points: list[tuple[datetime, dict[str, Any]]] = []
    zone = zoneinfo_for("CST")
    for point in points:
        parsed = parse_datetime(point.get("ts"), timezone="CST")
        value = _to_number(point.get("value"))
        if parsed is None or value is None:
            continue
        if unit == "percent" and abs(value) <= 1:
            value *= 100
        parsed_points.append(
            (
                parsed,
                {
                    "ts": str(point.get("ts")),
                    "label": parsed.astimezone(zone).strftime("%H:%M"),
                    "value": round(value, 2),
                    "raw_value": round(value, 2),
                },
            )
        )
    return [point for _, point in sorted(parsed_points, key=lambda item: item[0])]


def _timezone(response_json: dict[str, Any]) -> str:
    metadata = response_json.get("metadata")
    if isinstance(metadata, dict) and metadata.get("timezone"):
        return str(metadata["timezone"])
    return "CST"


def _summary_rows_with_real_hierarchy(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    has_web_hierarchy = any(
        row.get("parent_row_id") is not None
        or row.get("depth") is not None
        or row.get("is_expandable") is not None
        for row in rows
    )
    if not has_web_hierarchy:
        return [_flat_summary_row(row) for row in rows]

    normalized = [_with_hierarchy_defaults(row) for row in rows]
    children_by_parent: dict[str, int] = {}
    for row in normalized:
        parent = row.get("parent_row_id")
        if parent is not None:
            children_by_parent[str(parent)] = children_by_parent.get(str(parent), 0) + 1
    for row in normalized:
        row_id = str(row.get("row_id") or "")
        children_count = children_by_parent.get(row_id, 0)
        row["children_count"] = children_count
        row["is_expandable"] = bool(row.get("is_expandable")) and children_count > 0
        if not row["is_expandable"]:
            row["is_expanded_default"] = False
    return normalized


def _flat_summary_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        **row,
        "row_id": None,
        "parent_row_id": None,
        "depth": 0,
        "is_expandable": False,
        "is_expanded_default": False,
        "children_count": 0,
    }
    normalized.update(_semantic_states(normalized))
    return normalized


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
