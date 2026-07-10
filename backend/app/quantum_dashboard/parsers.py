from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

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
from backend.app.quantum_dashboard.contracts import (
    ChartLegendContract,
    ChartType,
    ContractResolution,
    DisplayNumberContract,
    DisplayUnit,
    HistoricalComparisonContract,
    QuantumBandContract,
    QuantumChartContract,
    QuantumSeriesContract,
    QuantumTableColumnContract,
    QuantumTableContract,
    SemanticIntent,
    SeriesKind,
    SortDirection,
    TableDataType,
)
from backend.app.quantum_dashboard.generic_roles import is_generic_role
from backend.app.quantum_dashboard.models import ChartAxis, ParserResult, VisualRole
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


def resolve_primary_value_from_contract(
    call: dict[str, Any],
    response_json: dict[str, Any],
) -> ContractResolution:
    visual = _visual_contract(call)
    explicit_candidates = [
        visual.get("value"),
        visual.get("display"),
        call.get("value_contract"),
        response_json.get("value_contract"),
        response_json.get("display"),
        response_json.get("primary_value"),
    ]
    resolved: list[DisplayNumberContract] = []
    for candidate in explicit_candidates:
        if not isinstance(candidate, dict):
            continue
        parsed = _display_contract_from_mapping(candidate, call)
        if parsed is not None:
            resolved.append(parsed)
    resolved = _dedupe_display_contracts(resolved)
    if len(resolved) == 1:
        return ContractResolution(
            status="resolved",
            value=resolved[0],
            evidence=["explicit_display_contract"],
        )
    if len(resolved) > 1:
        return ContractResolution(
            status="ambiguous",
            evidence=["multiple_explicit_display_contracts"],
            error="Quantum exposed conflicting primary value contracts.",
        )

    explicit_values = [
        _to_number(response_json.get(key))
        for key in ("visible_value", "main_value", "display_value", "total", "value")
    ]
    numeric_values = _dedupe_numbers([value for value in explicit_values if value is not None])
    evidence = "explicit_response_aggregate"
    if not numeric_values:
        aggregate = _single_aggregate_metric(response_json)
        numeric_values = [] if aggregate is None else [aggregate]
        evidence = "single_metric_aggregate_response"
    if len(numeric_values) > 1:
        return ContractResolution(
            status="ambiguous",
            evidence=["conflicting_explicit_aggregate_values"],
            error="Quantum exposed more than one possible primary value.",
        )
    if not numeric_values:
        return ContractResolution(
            status="missing",
            evidence=["no_explicit_primary_value"],
            error="No explicit aggregate or visible primary value was captured.",
        )
    unit: DisplayUnit = _explicit_unit(call, visual)
    value = numeric_values[0]
    scale = _to_number(visual.get("scale")) or 1
    display_value = value * scale
    return ContractResolution(
        status="resolved",
        value=DisplayNumberContract(
            raw_value=value,
            display_value=display_value,
            unit=unit,
            scale=scale,
            precision=_explicit_precision(call, visual, display_value),
            prefix=_text_value(visual.get("prefix")),
            suffix=_text_value(visual.get("suffix")),
            formatter=_text_value(visual.get("formatter")),
            formatted=_text_value(visual.get("formatted")),
        ),
        evidence=[evidence],
    )


def resolve_display_precision(
    call: dict[str, Any], response_json: dict[str, Any]
) -> ContractResolution:
    primary = resolve_primary_value_from_contract(call, response_json)
    if primary.status != "resolved" or not isinstance(primary.value, DisplayNumberContract):
        return ContractResolution(
            status=primary.status,
            evidence=primary.evidence,
            error=primary.error,
        )
    return ContractResolution(
        status="resolved",
        value=primary.value.precision,
        evidence=[*primary.evidence, "display_precision_from_contract"],
    )


def resolve_historical_comparison(
    call: dict[str, Any],
    response_json: dict[str, Any],
) -> ContractResolution:
    visual = _visual_contract(call)
    candidates = [visual.get("comparison"), response_json.get("comparison")]
    parsed: list[HistoricalComparisonContract] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        label = _text_value(candidate.get("label"))
        if not label:
            continue
        raw_delta = _first_number(candidate, "raw_delta", "delta", "delta_percent")
        display_delta = _first_number(
            candidate, "display_delta", "delta_percent", "display_value", "delta"
        )
        formatted = _text_value(candidate.get("formatted") or candidate.get("display"))
        precision = _int_value(candidate.get("precision"))
        if precision is None:
            precision = _precision_from_formatted(formatted)
        if precision is None:
            precision = _precision_from_number(display_delta)
        raw_intent = str(candidate.get("semantic_intent") or "neutral").strip().lower()
        intent: SemanticIntent = cast(SemanticIntent, raw_intent)
        if intent not in {"positive", "negative", "neutral"}:
            intent = "neutral"
        parsed.append(
            HistoricalComparisonContract(
                label=label,
                raw_delta=raw_delta,
                display_delta=display_delta,
                precision=precision,
                formatted=formatted,
                semantic_intent=intent,
            )
        )
    unique = {item.model_dump_json(): item for item in parsed}
    if len(unique) == 1:
        return ContractResolution(
            status="resolved",
            value=next(iter(unique.values())),
            evidence=["explicit_historical_comparison"],
        )
    if len(unique) > 1:
        return ContractResolution(
            status="ambiguous",
            evidence=["conflicting_historical_comparisons"],
            error="Quantum exposed conflicting historical comparisons.",
        )
    return ContractResolution(status="missing", evidence=["comparison_not_captured"])


def resolve_chart_contract(
    call: dict[str, Any],
    response_json: dict[str, Any],
) -> ContractResolution:
    visual = _visual_contract(call)
    candidate = (
        visual.get("chart") or response_json.get("chart_contract") or response_json.get("chart")
    )
    if not isinstance(candidate, dict):
        return ContractResolution(status="missing", evidence=["chart_contract_not_captured"])
    try:
        chart = _chart_contract_from_mapping(candidate, call, response_json)
    except (TypeError, ValueError) as exc:
        return ContractResolution(
            status="invalid",
            evidence=["invalid_explicit_chart_contract"],
            error=str(exc),
        )
    return ContractResolution(
        status="resolved",
        value=chart,
        evidence=["explicit_chart_contract"],
    )


def resolve_table_contract(
    call: dict[str, Any],
    response_json: dict[str, Any],
    parsed_rows: list[dict[str, Any]],
) -> ContractResolution:
    visual = _visual_contract(call)
    candidate = visual.get("table") or response_json.get("table_contract")
    columns_value = candidate.get("columns") if isinstance(candidate, dict) else None
    if columns_value is None:
        columns_value = response_json.get("columns") or response_json.get("columnNames")
    if not isinstance(columns_value, list) or not columns_value:
        return ContractResolution(
            status="missing",
            evidence=["table_columns_not_captured"],
            error="Quantum table headers were not captured with the response.",
        )
    try:
        columns = [_table_column_from_value(column) for column in columns_value]
    except ValueError as exc:
        return ContractResolution(
            status="invalid",
            evidence=["invalid_table_column_contract"],
            error=str(exc),
        )
    table_mapping = candidate if isinstance(candidate, dict) else {}
    rows = table_mapping.get("rows")
    if not isinstance(rows, list):
        rows = parsed_rows
    return ContractResolution(
        status="resolved",
        value=QuantumTableContract(
            columns=columns,
            rows=[row for row in rows if isinstance(row, dict)],
            default_sort_column=_text_value(table_mapping.get("default_sort_column")),
            default_sort_direction=_sort_direction(table_mapping.get("default_sort_direction")),
            period_label=_text_value(table_mapping.get("period_label") or call.get("period_label"))
            or "",
            timezone=_text_value(table_mapping.get("timezone") or call.get("range_timezone"))
            or "UTC",
        ),
        evidence=["explicit_table_column_contract"],
    )


def _parse_generic_metric(
    call: dict[str, Any],
    role: VisualRole,
    response_json: dict[str, Any],
) -> ParserResult:
    title = _generic_title(call, role)
    value_resolution = resolve_primary_value_from_contract(call, response_json)
    if value_resolution.status != "resolved" or not isinstance(
        value_resolution.value, DisplayNumberContract
    ):
        error_code = {
            "ambiguous": "failed_ambiguous_primary_value",
            "invalid": "failed_invalid_contract",
        }.get(value_resolution.status, "failed_missing_primary_value")
        return _error(
            role,
            error_code,
            value_resolution.error or f"No explicit primary value contract found for {role}.",
        )
    display = value_resolution.value
    comparison_resolution = resolve_historical_comparison(call, response_json)
    comparison = (
        comparison_resolution.value
        if isinstance(comparison_resolution.value, HistoricalComparisonContract)
        else None
    )
    chart_resolution = resolve_chart_contract(call, response_json)
    chart = (
        chart_resolution.value if isinstance(chart_resolution.value, QuantumChartContract) else None
    )
    widget: dict[str, Any] = {
        "id": role,
        "role": role,
        "title": title,
        "value": display.display_value,
        "display": display.model_dump(mode="json"),
        "unit": display.unit,
        "chart_type": chart.chart_type if chart else "kpi",
        "breakdown": [],
        "timeseries": _timeseries_from_chart(chart),
        "comparison": comparison.model_dump(mode="json") if comparison else None,
        "chart_payload": chart_payload_from_contract(chart) if chart else None,
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
    table_resolution = resolve_table_contract(call, response_json, parsed_rows)
    if table_resolution.status != "resolved" or not isinstance(
        table_resolution.value, QuantumTableContract
    ):
        return _error(
            role,
            "failed_invalid_contract"
            if table_resolution.status == "invalid"
            else "failed_missing_table_contract",
            table_resolution.error or "Quantum table column contract is missing.",
        )
    table = table_resolution.value
    columns = [column.model_dump(mode="json") for column in table.columns]
    widget = {
        "id": role,
        "role": role,
        "title": _generic_title(call, role),
        "value": None,
        "unit": "count",
        "chart_type": "table",
        "breakdown": [],
        "timeseries": [],
        "table_columns": columns,
        "table_rows": table.rows,
        "table_contract": table.model_dump(mode="json"),
        "comparison": None,
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
    value_resolution = resolve_primary_value_from_contract(call, response_json)
    chart_resolution = resolve_chart_contract(call, response_json)
    if value_resolution.status != "resolved" or not isinstance(
        value_resolution.value, DisplayNumberContract
    ):
        return _error(
            role,
            "failed_ambiguous_primary_value"
            if value_resolution.status == "ambiguous"
            else "failed_missing_primary_value",
            value_resolution.error or "Generic donut needs an explicit total contract.",
        )
    if chart_resolution.status != "resolved" or not isinstance(
        chart_resolution.value, QuantumChartContract
    ):
        return _error(
            role,
            "failed_invalid_chart_contract"
            if chart_resolution.status == "invalid"
            else "failed_missing_chart_contract",
            chart_resolution.error or "Generic donut needs an explicit chart contract.",
        )
    display = value_resolution.value
    chart = chart_resolution.value
    title = _generic_title(call, role)
    widget: dict[str, Any] = {
        "id": role,
        "role": role,
        "title": title,
        "chart_type": "donut",
        "total": display.display_value,
        "value": display.display_value,
        "display": display.model_dump(mode="json"),
        "unit": display.unit,
        "series": [],
        "chart_payload": chart_payload_from_contract(chart),
        "comparison": None,
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
    value_resolution = resolve_primary_value_from_contract(
        {**call, "unit": call.get("unit") or spec.unit}, response_json
    )
    if value_resolution.status != "resolved" or not isinstance(
        value_resolution.value, DisplayNumberContract
    ):
        return _error(
            role,
            "failed_ambiguous_primary_value"
            if value_resolution.status == "ambiguous"
            else "failed_missing_primary_value",
            value_resolution.error or f"No explicit aggregate value found for {role}.",
        )
    display = value_resolution.value
    timeseries = _timeseries(response_json, metric_aliases)

    widget = {
        "id": spec.local_id,
        "role": role,
        "title": spec.title,
        "value": display.display_value,
        "display": display.model_dump(mode="json"),
        "unit": display.unit,
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
            parsed["error_session_percent"] = _metric_at(row, 0)
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
            parsed["error_session_percent"] = _metric_at(row, 0)
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


def _visual_contract(call: dict[str, Any]) -> dict[str, Any]:
    value = call.get("visual_contract") or call.get("widget_contract")
    if isinstance(value, dict):
        return value
    return parse_json_object(value)


def _display_contract_from_mapping(
    candidate: dict[str, Any],
    call: dict[str, Any],
) -> DisplayNumberContract | None:
    raw_value = _first_number(candidate, "raw_value", "raw", "value")
    display_value = _first_number(candidate, "display_value", "display", "value")
    formatted = _text_value(candidate.get("formatted"))
    if raw_value is None and display_value is None and formatted is None:
        return None
    scale = _to_number(candidate.get("scale")) or 1
    if display_value is None and raw_value is not None:
        display_value = raw_value * scale
    if raw_value is None and display_value is not None:
        raw_value = display_value / scale
    unit = _normalize_unit(candidate.get("unit"), candidate.get("suffix"))
    if unit is None:
        unit = _explicit_unit(call, _visual_contract(call))
    precision = _int_value(candidate.get("precision"))
    if precision is None:
        precision = _precision_from_formatted(formatted)
    if precision is None:
        precision = _precision_from_number(display_value)
    return DisplayNumberContract(
        raw_value=raw_value,
        display_value=display_value,
        unit=unit,
        scale=scale,
        precision=precision,
        prefix=_text_value(candidate.get("prefix")),
        suffix=_text_value(candidate.get("suffix")),
        formatter=_text_value(candidate.get("formatter")),
        formatted=formatted,
    )


def _chart_contract_from_mapping(
    candidate: dict[str, Any],
    call: dict[str, Any],
    response_json: dict[str, Any],
) -> QuantumChartContract:
    raw_chart_type = str(candidate.get("chart_type") or candidate.get("type") or "").lower()
    chart_type: ChartType = cast(ChartType, raw_chart_type)
    if chart_type not in {"line", "bar", "area", "stacked_bar", "donut", "mixed"}:
        raise ValueError("Quantum chart_type is missing or unsupported.")
    series_values = candidate.get("series")
    if not isinstance(series_values, list):
        raise ValueError("Quantum chart series contract is missing.")
    series: list[QuantumSeriesContract] = []
    for index, value in enumerate(series_values):
        if not isinstance(value, dict):
            raise ValueError("Quantum chart series entry is invalid.")
        series_id = _text_value(value.get("series_id") or value.get("id"))
        label = _text_value(value.get("label") or value.get("name"))
        raw_kind = str(value.get("kind") or "").lower()
        kind: SeriesKind = cast(SeriesKind, raw_kind)
        if (
            not series_id
            or not label
            or kind
            not in {
                "line",
                "bar",
                "area",
                "baseline",
                "band",
                "anomaly",
            }
        ):
            raise ValueError("Quantum chart series identity, label or kind is incomplete.")
        points = value.get("points")
        if not points and kind in {"line", "bar", "area"}:
            points = _chart_points_from_response(candidate, call, response_json)
        series.append(
            QuantumSeriesContract(
                series_id=series_id,
                label=label,
                kind=kind,
                order=_int_value(value.get("order")) or index,
                points=points if isinstance(points, list) else [],
                visible=value.get("visible") is not False,
                style=_text_value(value.get("style")),
            )
        )
    bands: list[QuantumBandContract] = []
    for index, value in enumerate(candidate.get("bands") or []):
        if not isinstance(value, dict):
            raise ValueError("Quantum chart band entry is invalid.")
        band_id = _text_value(value.get("band_id") or value.get("id")) or f"band-{index}"
        label = _text_value(value.get("label") or value.get("name"))
        raw_band_kind = str(value.get("kind") or value.get("purpose") or "custom").lower()
        if not label or raw_band_kind not in {
            "historical_range",
            "anomaly",
            "confidence",
            "custom",
        }:
            raise ValueError("Quantum chart band identity is incomplete.")
        bands.append(
            QuantumBandContract(
                band_id=band_id,
                label=label,
                kind=cast(Any, raw_band_kind),
                start=_text_value(value.get("start") or value.get("start_ts")),
                end=_text_value(value.get("end") or value.get("end_ts")),
                lower_points=value.get("lower_points") or [],
                upper_points=value.get("upper_points") or [],
                pattern=_text_value(value.get("pattern")),
            )
        )
    legends: list[ChartLegendContract] = []
    for index, value in enumerate(candidate.get("legends") or []):
        if not isinstance(value, dict):
            raise ValueError("Quantum chart legend entry is invalid.")
        legend_id = _text_value(value.get("id"))
        label = _text_value(value.get("label"))
        raw_legend_kind = str(value.get("kind") or "").lower() or None
        if not legend_id or not label:
            raise ValueError("Quantum chart legend identity is incomplete.")
        legends.append(
            ChartLegendContract(
                id=legend_id,
                label=label,
                order=_int_value(value.get("order")) or index,
                kind=cast(SeriesKind | None, raw_legend_kind),
                visible=value.get("visible") is not False,
            )
        )
    return QuantumChartContract(
        chart_type=chart_type,
        x_axis=ChartAxis.model_validate(candidate.get("x_axis") or {"ticks": []}),
        y_axis=ChartAxis.model_validate(candidate.get("y_axis") or {"ticks": []}),
        series=series,
        bands=bands,
        legends=legends,
        period_label=_text_value(candidate.get("period_label") or call.get("period_label")) or "",
        timezone=_text_value(candidate.get("timezone") or call.get("range_timezone")) or "UTC",
        granularity=_text_value(candidate.get("granularity")) or "captured",
    )


def _table_column_from_value(value: Any) -> QuantumTableColumnContract:
    if isinstance(value, str):
        key = canonicalize_key(value)
        return QuantumTableColumnContract(key=key, label=value, data_type="text")
    if not isinstance(value, dict):
        raise ValueError("Quantum table column entry is invalid.")
    key_text = _text_value(value.get("key") or value.get("name"))
    label = _text_value(value.get("label") or value.get("title"))
    if not key_text or not label:
        raise ValueError("Quantum table column key or label is missing.")
    raw_data_type = str(value.get("data_type") or value.get("type") or "text").lower()
    if raw_data_type not in {"text", "number", "percent", "datetime"}:
        raw_data_type = "text"
    data_type: TableDataType = cast(TableDataType, raw_data_type)
    return QuantumTableColumnContract(
        key=key_text,
        label=label,
        data_type=data_type,
        precision=_int_value(value.get("precision")),
        sortable=bool(value.get("sortable")),
        default_sort=_sort_direction(value.get("default_sort")),
    )


def chart_payload_from_contract(chart: QuantumChartContract) -> dict[str, Any]:
    return {
        "chart_type": chart.chart_type,
        "x_axis": chart.x_axis.model_dump(mode="json"),
        "y_axis": chart.y_axis.model_dump(mode="json"),
        "series": [
            {
                "id": item.series_id,
                "label": item.label,
                "kind": item.kind,
                "order": item.order,
                "points": [point.model_dump(mode="json") for point in item.points],
                "visible": item.visible,
                "style": item.style,
            }
            for item in chart.series
        ],
        "bands": [
            {
                "id": item.band_id,
                "label": item.label,
                "kind": item.kind,
                "start_ts": item.start,
                "end_ts": item.end,
                "lower_points": [point.model_dump(mode="json") for point in item.lower_points],
                "upper_points": [point.model_dump(mode="json") for point in item.upper_points],
                "pattern": item.pattern,
                "purpose": item.kind,
            }
            for item in chart.bands
        ],
        "legends": [item.model_dump(mode="json") for item in chart.legends],
        "period_label": chart.period_label,
        "granularity": chart.granularity,
        "timezone": chart.timezone,
    }


def _chart_points_from_response(
    candidate: dict[str, Any],
    call: dict[str, Any],
    response_json: dict[str, Any],
) -> list[dict[str, Any]]:
    source = sorted(
        _timeseries(response_json, ()),
        key=lambda point: _timeseries_sort_key(point.get("ts")),
    )
    if not source:
        return []
    visual = _visual_contract(call)
    scale = _to_number(visual.get("scale")) or 1
    axis = candidate.get("x_axis")
    ticks = axis.get("ticks") if isinstance(axis, dict) else []
    labels = [
        _text_value(tick.get("label")) if isinstance(tick, dict) else _text_value(tick)
        for tick in ticks or []
    ]
    denominator = max(1, len(source) - 1)
    return [
        {
            "ts": str(point.get("ts") or ""),
            "label": labels[index] if index < len(labels) and labels[index] else str(point["ts"]),
            "raw_value": float(point["value"]),
            "value": float(point["value"]) * scale,
            "x": index / denominator,
        }
        for index, point in enumerate(source)
    ]


def _timeseries_sort_key(value: Any) -> tuple[int, float | str]:
    number = _to_number(value)
    return (0, number) if number is not None else (1, str(value or ""))


def _timeseries_from_chart(chart: QuantumChartContract | None) -> list[dict[str, Any]]:
    if chart is None:
        return []
    return [
        {**point.model_dump(mode="json"), "series": series.label}
        for series in chart.series
        for point in series.points
    ]


def _single_aggregate_metric(response_json: dict[str, Any]) -> float | None:
    rows = response_json.get("rows")
    if isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict):
        dimensions = rows[0].get("dimensions")
        metrics = rows[0].get("metrics")
        if dimensions in (None, []) and isinstance(metrics, list) and len(metrics) == 1:
            value = metrics[0]
            if isinstance(value, list) and len(value) == 1:
                value = value[0]
            return _to_number(value)
    results = response_json.get("results")
    if isinstance(results, list) and len(results) == 1 and isinstance(results[0], list):
        dimensions = results[0][0] if results[0] else None
        metrics = results[0][1] if len(results[0]) > 1 else None
        if dimensions in (None, []) and isinstance(metrics, list) and len(metrics) == 1:
            value = metrics[0]
            if isinstance(value, list) and len(value) == 1:
                value = value[0]
            return _to_number(value)
    return None


def _explicit_unit(call: dict[str, Any], visual: dict[str, Any]) -> DisplayUnit:
    return _normalize_unit(call.get("unit") or visual.get("unit"), visual.get("suffix")) or "count"


def _normalize_unit(value: Any, suffix: Any = None) -> DisplayUnit | None:
    raw = str(value or "").strip().lower()
    aliases = {
        "number": "count",
        "integer": "count",
        "duration": "seconds",
        "second": "seconds",
        "%": "percent",
    }
    raw = aliases.get(raw, raw)
    if raw in {"count", "score", "percent", "seconds", "text"}:
        return cast(DisplayUnit, raw)
    if _text_value(suffix) == "%":
        return "percent"
    return None


def _explicit_precision(call: dict[str, Any], visual: dict[str, Any], value: float) -> int:
    precision = _int_value(call.get("precision") or visual.get("precision"))
    return precision if precision is not None else _precision_from_number(value)


def _precision_from_formatted(value: str | None) -> int | None:
    if not value:
        return None
    numeric = value.strip().replace("%", "").replace(",", "")
    if "." not in numeric:
        return 0 if any(character.isdigit() for character in numeric) else None
    decimals = numeric.rsplit(".", 1)[1]
    return len("".join(character for character in decimals if character.isdigit()))


def _precision_from_number(value: float | None) -> int:
    if value is None:
        return 0
    text = format(value, ".12f").rstrip("0").rstrip(".")
    return len(text.rsplit(".", 1)[1]) if "." in text else 0


def _first_number(value: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        parsed = _to_number(value.get(key))
        if parsed is not None:
            return parsed
    return None


def _int_value(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _sort_direction(value: Any) -> SortDirection | None:
    text = str(value or "").strip().lower()
    return cast(SortDirection, text) if text in {"asc", "desc"} else None


def _dedupe_numbers(values: list[float]) -> list[float]:
    return list(dict.fromkeys(values))


def _dedupe_display_contracts(
    values: list[DisplayNumberContract],
) -> list[DisplayNumberContract]:
    by_payload = {value.model_dump_json(): value for value in values}
    return list(by_payload.values())


def _sort_number(value: object) -> float:
    parsed = _to_number(value)
    return parsed if parsed is not None else -1.0


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
