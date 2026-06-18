from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from backend.app.analytics.normalizer import canonicalize_key, parse_json_object
from backend.app.quantum_dashboard.card_mapper import card_title_for_role, map_card_role
from backend.app.quantum_dashboard.catalog import ROLE_SPECS, required_roles
from backend.app.quantum_dashboard.models import (
    CardContract,
    DashboardPeriod,
    DerivedBuildResult,
    ParserResult,
    RegressionStatus,
    VisualRole,
    WebSnapshot,
)
from backend.app.quantum_dashboard.parsers import parse_card
from backend.app.quantum_dashboard.periods import format_period_label, parse_datetime
from backend.app.quantum_dashboard.semantics import semantic_intent, semantic_state
from backend.app.storage.parquet_store import ParquetStore, hash_json

DATASET_VISUAL_CONTRACTS = "visual_contracts"
DATASET_DASHBOARD_CARDS = "dashboard_cards"
DATASET_WEB_SNAPSHOTS = "web_snapshots"
DATASET_SUMMARY_WIDGETS = "derived/summary_widgets"
DATASET_SUMMARY_TABLE = "derived/summary_detail_table"
DATASET_ERRORS_WIDGETS = "derived/errors_widgets"
DATASET_ERRORS_TOP_ERRORS = "derived/errors_top_errors_table"
DATASET_ERRORS_APP_NAME = "derived/errors_app_name_table"
DATASET_TIMESERIES = "derived/timeseries"
DATASET_CHART_PAYLOADS = "derived/chart_payloads"
DATASET_REGRESSION_RESULTS = "regression/web_vs_local_results"
DATASET_REGRESSION_DISCREPANCIES = "regression/discrepancies"
REQUIRED_CHART_ROLES: set[VisualRole] = {
    "summary.page_views",
    "summary.sessions",
    "summary.converted_sessions",
    "summary.avg_session_duration",
    "errors.error_sessions_percentage_evolution",
    "errors.error_sessions_by_app_name_comparison",
}


def build_derived_datasets(
    store: ParquetStore,
    country: str,
    *,
    raw_calls: list[dict[str, Any]] | None = None,
    ingestion_id: str | None = None,
    enabled_roles: set[str] | list[str] | None = None,
) -> DerivedBuildResult:
    calls = raw_calls if raw_calls is not None else _read_raw_calls(store, country)
    enabled_role_set: set[str] = (
        set(enabled_roles)
        if enabled_roles is not None
        else {str(role) for role in required_roles()}
    )
    selected = _latest_call_by_role(calls)
    selected = {role: call for role, call in selected.items() if str(role) in enabled_role_set}
    timeseries_by_role = _timeseries_call_by_role(calls)
    timeseries_by_role = {
        role: call for role, call in timeseries_by_role.items() if str(role) in enabled_role_set
    }
    now = datetime.now(UTC).isoformat()
    contracts: list[CardContract] = []
    snapshots: list[WebSnapshot] = []
    summary_widgets: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    errors_widgets: list[dict[str, Any]] = []
    top_error_rows: list[dict[str, Any]] = []
    error_app_rows: list[dict[str, Any]] = []
    timeseries_rows: list[dict[str, Any]] = []
    chart_payload_rows: list[dict[str, Any]] = []
    parser_errors: list[dict[str, str]] = []

    for role, call in selected.items():
        contract = _contract_from_call(country, role, call, now)
        result = parse_card(call, role)
        if result.status != "ok":
            parser_errors.append(
                {
                    "card_role": role,
                    "card_title": contract.card_title,
                    "error_code": result.error_code or "parse_error",
                    "error_message": result.error_message or "Parser failed.",
                }
            )
            continue

        result = _with_related_timeseries(result, timeseries_by_role.get(role), role)

        contracts.append(contract)
        snapshots.append(_snapshot_from_result(country, contract, result, call, now))
        _append_derived_rows(
            role=role,
            contract=contract,
            result=result,
            summary_widgets=summary_widgets,
            summary_rows=summary_rows,
            errors_widgets=errors_widgets,
            top_error_rows=top_error_rows,
            error_app_rows=error_app_rows,
            timeseries_rows=timeseries_rows,
            chart_payload_rows=chart_payload_rows,
        )

    validation_errors = _validate_required_chart_payloads(
        selected, summary_widgets, errors_widgets, enabled_role_set
    )
    parser_errors.extend(validation_errors)

    store.write_country_dataset(
        country,
        DATASET_VISUAL_CONTRACTS,
        [contract.model_dump(mode="json") for contract in contracts],
        file_name="visual_contracts.parquet",
    )
    store.write_country_dataset(
        country,
        DATASET_DASHBOARD_CARDS,
        [_dashboard_card_row(contract) for contract in contracts],
        file_name="dashboard_cards.parquet",
    )
    store.write_country_dataset(
        country,
        DATASET_WEB_SNAPSHOTS,
        [snapshot.model_dump(mode="json") for snapshot in snapshots],
        file_name="web_snapshots.parquet",
    )
    store.write_country_dataset(country, DATASET_SUMMARY_WIDGETS, summary_widgets)
    store.write_country_dataset(country, DATASET_SUMMARY_TABLE, summary_rows)
    store.write_country_dataset(country, DATASET_ERRORS_WIDGETS, errors_widgets)
    store.write_country_dataset(country, DATASET_ERRORS_TOP_ERRORS, top_error_rows)
    store.write_country_dataset(country, DATASET_ERRORS_APP_NAME, error_app_rows)
    store.write_country_dataset(country, DATASET_TIMESERIES, timeseries_rows)
    store.write_country_dataset(country, DATASET_CHART_PAYLOADS, chart_payload_rows)

    expected_roles = [role for role in required_roles() if str(role) in enabled_role_set]
    missing = [role for role in expected_roles if role not in selected]
    mandatory_captured = len([role for role in expected_roles if role in selected])
    regression_status: RegressionStatus = (
        "passed" if not missing and not parser_errors else "failed_missing_card"
    )
    if parser_errors:
        regression_status = "failed_parse_error"
    if validation_errors:
        regression_status = "failed_missing_chart_payload"

    return DerivedBuildResult(
        ingestion_id=ingestion_id,
        country=country,
        raw_calls=len(calls),
        raw_rows=sum(int(call.get("row_count") or 0) for call in calls),
        captured_cards=len(selected),
        mandatory_cards=len(expected_roles),
        mandatory_cards_captured=mandatory_captured,
        derived_datasets=sum(
            bool(rows)
            for rows in (
                summary_widgets,
                summary_rows,
                errors_widgets,
                top_error_rows,
                error_app_rows,
                timeseries_rows,
                chart_payload_rows,
            )
        ),
        missing_roles=[str(role) for role in missing],
        parser_errors=parser_errors,
        regression_status=regression_status,
    )


def _latest_call_by_role(calls: list[dict[str, Any]]) -> dict[VisualRole, dict[str, Any]]:
    selected: dict[VisualRole, dict[str, Any]] = {}
    scores: dict[VisualRole, int] = {}
    for call in calls:
        role = map_card_role(call)
        if role is None:
            continue
        score = _call_score(role, call)
        if role not in selected or score >= scores[role]:
            selected[role] = {**call, "card_role": role}
            scores[role] = score
    return selected


def _timeseries_call_by_role(calls: list[dict[str, Any]]) -> dict[VisualRole, dict[str, Any]]:
    selected: dict[VisualRole, dict[str, Any]] = {}
    scores: dict[VisualRole, int] = {}
    last_role_by_card: dict[str, VisualRole] = {}
    for call in calls:
        role = map_card_role(call)
        card_id = _text(call.get("card_id"))
        view_name = str(call.get("view_name") or "")
        if role is not None and card_id:
            last_role_by_card[card_id] = role
        if "timeSeriesQuery" not in view_name:
            continue
        inferred_role = role
        if inferred_role is None and card_id:
            inferred_role = last_role_by_card.get(card_id)
        if inferred_role is None:
            continue
        score = _timeseries_score(call)
        if inferred_role not in selected or score >= scores[inferred_role]:
            selected[inferred_role] = {**call, "card_role": inferred_role}
            scores[inferred_role] = score
    return selected


def _timeseries_score(call: dict[str, Any]) -> int:
    view_name = str(call.get("view_name") or "")
    score = int(call.get("row_count") or 0)
    if "ComparisonSegment" in view_name:
        score += 200
    if ":historical" not in view_name:
        score += 100
    return score


def _with_related_timeseries(
    result: ParserResult,
    timeseries_call: dict[str, Any] | None,
    role: VisualRole,
) -> ParserResult:
    if timeseries_call is None:
        return result
    parsed = parse_card(timeseries_call, role)
    widget = result.data.get("widget")
    timeseries_widget = parsed.data.get("widget") if parsed.status == "ok" else None
    if not isinstance(widget, dict) or not isinstance(timeseries_widget, dict):
        return result
    timeseries = timeseries_widget.get("timeseries")
    if isinstance(timeseries, list) and timeseries:
        widget["timeseries"] = timeseries
    chart_payload = timeseries_widget.get("chart_payload")
    if isinstance(chart_payload, dict) and chart_payload.get("series"):
        widget["chart_payload"] = chart_payload
    period = _period_from_call(timeseries_call)
    if period:
        widget["period"] = period
        payload = widget.get("chart_payload")
        if isinstance(payload, dict):
            payload["timezone"] = period.get("timezone") or payload.get("timezone")
    return ParserResult(role=result.role, status=result.status, data=result.data)


def _call_score(role: VisualRole, call: dict[str, Any]) -> int:
    view_name = str(call.get("view_name") or "")
    score = int(call.get("row_count") or 0)
    if role in {
        "summary.detail_by_app_name_os",
        "errors.top_errors_by_error_name",
        "errors.error_session_percentage_by_app_name",
    }:
        if view_name == "table":
            score += 1000
        if view_name == "topN":
            score += 900
    else:
        if view_name in {"coreMetricsComparisonSegment", "dimensionQueryComparisonSegment"}:
            score += 1200
        if view_name in {"coreMetrics", "dimensionQuery"}:
            score += 1000
        if view_name.endswith(":historical"):
            score += 100
        if "timeSeriesQuery" in view_name:
            score += 50
    if call.get("metric_ids") not in (None, "", "[]"):
        score += 25
    return score


def _contract_from_call(
    country: str,
    role: VisualRole,
    call: dict[str, Any],
    discovered_at: str,
) -> CardContract:
    spec = ROLE_SPECS[role]
    request_json = parse_json_object(call.get("request_json"))
    response_json = parse_json_object(call.get("response_json"))
    metadata = _metadata(request_json)
    metric_ids = _metric_ids(call.get("metric_ids"), metadata.get("metricIds"))
    dimensions = _query_dimensions(request_json)
    period = _period_from_call(call)
    return CardContract(
        country=country,
        dashboard_id=_text(call.get("dashboard_id") or metadata.get("dashboardId")),
        team_id=_text(call.get("team_id") or metadata.get("teamId") or metadata.get("teamID")),
        tab=spec.tab,
        tab_name="Resumen" if spec.tab == "summary" else "Errores",
        card_id=_text(call.get("card_id") or metadata.get("cardId")) or f"mapped:{role}",
        card_title=card_title_for_role(role, call),
        card_type=_text(call.get("card_type") or metadata.get("cardType")) or spec.card_type,
        visual_role=role,
        source_endpoint=_text(call.get("endpoint") or call.get("source_endpoint")) or "unknown",
        request_hash=_text(call.get("query_hash")) or hash_json(request_json),
        response_hash=_text(call.get("response_hash")) or hash_json(response_json),
        metric_ids=metric_ids,
        dimensions=dimensions,
        period=DashboardPeriod(
            start=period.get("start") if period else _text(call.get("source_ts_start")),
            end=period.get("end") if period else _text(call.get("source_ts_end")),
            timezone=(period.get("timezone") if period else None)
            or _text(metadata.get("timezone"))
            or "CST",
        ),
        parse_strategy=spec.parse_strategy,
        chart_type=spec.card_type,
        columns=_response_columns(response_json),
        measures=metric_ids,
        required=spec.required,
        discovered_at=discovered_at,
    )


def _snapshot_from_result(
    country: str,
    contract: CardContract,
    result: ParserResult,
    call: dict[str, Any],
    captured_at: str,
) -> WebSnapshot:
    widget_value = result.data.get("widget")
    rows_value = result.data.get("rows")
    columns_value = result.data.get("columns")
    widget = widget_value if isinstance(widget_value, dict) else {}
    rows = rows_value if isinstance(rows_value, list) else []
    columns = columns_value if isinstance(columns_value, list) else []
    visible_value = widget.get("value")
    if visible_value is None:
        visible_value = widget.get("total")
    return WebSnapshot(
        ingestion_id=str(call.get("ingestion_id") or ""),
        country=country,
        dashboard_id=contract.dashboard_id,
        team_id=contract.team_id,
        tab=contract.tab,
        card_role=contract.visual_role,
        card_title=contract.card_title,
        visible_value=visible_value,
        visible_breakdowns=_list_of_dicts(widget.get("breakdown") or widget.get("series")),
        visible_series=_list_of_dicts(widget.get("timeseries") or widget.get("series")),
        visible_table_columns=[str(column) for column in columns],
        visible_table_rows=_list_of_dicts(rows[:10]),
        captured_at=captured_at,
    )


def _append_derived_rows(
    *,
    role: VisualRole,
    contract: CardContract,
    result: ParserResult,
    summary_widgets: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]],
    errors_widgets: list[dict[str, Any]],
    top_error_rows: list[dict[str, Any]],
    error_app_rows: list[dict[str, Any]],
    timeseries_rows: list[dict[str, Any]],
    chart_payload_rows: list[dict[str, Any]],
) -> None:
    widget = result.data.get("widget")
    rows = result.data.get("rows")
    if isinstance(widget, dict):
        row = _widget_row(contract, widget)
        if contract.tab == "summary":
            summary_widgets.append(row)
        else:
            errors_widgets.append(row)
        for point in _list_of_dicts(widget.get("timeseries")):
            timeseries_rows.append(
                {
                    "country": contract.country,
                    "card_role": role,
                    "card_title": contract.card_title,
                    "ts": point.get("ts"),
                    "value": point.get("value"),
                    "unit": widget.get("unit"),
                }
            )
        chart_payload = widget.get("chart_payload")
        if isinstance(chart_payload, dict):
            chart_payload_rows.append(_chart_payload_row(contract, widget, chart_payload))
    if isinstance(rows, list):
        for index, item in enumerate(_list_of_dicts(rows)):
            row = {
                **item,
                "country": contract.country,
                "card_role": role,
                "card_title": contract.card_title,
                "row_index": index,
            }
            if role == "summary.detail_by_app_name_os":
                summary_rows.append(row)
            elif role == "errors.top_errors_by_error_name":
                top_error_rows.append(row)
            elif role == "errors.error_session_percentage_by_app_name":
                error_app_rows.append(row)


def _widget_row(contract: CardContract, widget: dict[str, Any]) -> dict[str, Any]:
    raw_widget_period = widget.get("period")
    widget_period: dict[str, Any] = raw_widget_period if isinstance(raw_widget_period, dict) else {}
    period_label = _period_label(
        widget_period.get("start") or contract.period.start,
        widget_period.get("end") or contract.period.end,
        widget_period.get("timezone") or contract.period.timezone,
    )
    chart_payload = widget.get("chart_payload")
    if isinstance(chart_payload, dict):
        chart_payload = dict(chart_payload)
        chart_payload["period_label"] = chart_payload.get("period_label") or period_label
        chart_payload["timezone"] = (
            chart_payload.get("timezone")
            or widget_period.get("timezone")
            or contract.period.timezone
        )
    comparison = widget.get("comparison") if isinstance(widget.get("comparison"), dict) else {}
    delta_percent = comparison.get("delta_percent") if isinstance(comparison, dict) else None
    metric_id = str(widget.get("id") or contract.visual_role.split(".")[-1])
    return {
        "country": contract.country,
        "card_role": contract.visual_role,
        "card_title": contract.card_title,
        "id": widget.get("id"),
        "title": widget.get("title"),
        "value": widget.get("value"),
        "unit": widget.get("unit"),
        "chart_type": widget.get("chart_type"),
        "total": widget.get("total"),
        "breakdown": widget.get("breakdown", []),
        "series": widget.get("series", []),
        "timeseries": widget.get("timeseries", []),
        "chart_payload": chart_payload,
        "comparison": widget.get("comparison"),
        "delta_percent": delta_percent,
        "semantic_state": semantic_state(metric_id, _float_or_none(delta_percent)),
        "semantic_intent": semantic_intent(metric_id, _float_or_none(delta_percent)),
        "period_start": widget_period.get("start") or contract.period.start,
        "period_end": widget_period.get("end") or contract.period.end,
        "period_timezone": widget_period.get("timezone") or contract.period.timezone,
        "period_label": period_label,
        "regression_source": "web_snapshot",
    }


def _chart_payload_row(
    contract: CardContract,
    widget: dict[str, Any],
    chart_payload: dict[str, Any],
) -> dict[str, Any]:
    raw_widget_period = widget.get("period")
    widget_period: dict[str, Any] = raw_widget_period if isinstance(raw_widget_period, dict) else {}
    payload = dict(chart_payload)
    payload["period_label"] = payload.get("period_label") or _period_label(
        widget_period.get("start") or contract.period.start,
        widget_period.get("end") or contract.period.end,
        widget_period.get("timezone") or contract.period.timezone,
    )
    return {
        "country": contract.country,
        "ingestion_id": "",
        "dashboard_id": contract.dashboard_id,
        "team_id": contract.team_id,
        "tab": contract.tab,
        "card_id": contract.card_id,
        "card_role": contract.visual_role,
        "card_title": contract.card_title,
        "chart_type": payload.get("chart_type"),
        "chart_payload": payload,
        "source_query_hash": contract.request_hash,
        "source_response_hash": contract.response_hash,
        "period_start": widget_period.get("start") or contract.period.start,
        "period_end": widget_period.get("end") or contract.period.end,
        "timezone": widget_period.get("timezone") or contract.period.timezone,
        "period_label": payload["period_label"],
        "regression_status": "pending",
    }


def _validate_required_chart_payloads(
    selected: dict[VisualRole, dict[str, Any]],
    summary_widgets: list[dict[str, Any]],
    errors_widgets: list[dict[str, Any]],
    enabled_roles: set[str],
) -> list[dict[str, str]]:
    widgets = {str(row.get("card_role")): row for row in [*summary_widgets, *errors_widgets]}
    errors: list[dict[str, str]] = []
    for role in REQUIRED_CHART_ROLES:
        if str(role) not in enabled_roles:
            continue
        if role not in selected:
            continue
        payload = widgets.get(role, {}).get("chart_payload")
        if not isinstance(payload, dict) or not payload.get("series"):
            errors.append(
                {
                    "card_role": role,
                    "card_title": card_title_for_role(role, selected[role]),
                    "error_code": "failed_missing_chart_payload",
                    "error_message": "Required chart card has no complete chart_payload.",
                }
            )
            continue
        if not payload.get("period_label"):
            errors.append(
                {
                    "card_role": role,
                    "card_title": card_title_for_role(role, selected[role]),
                    "error_code": "failed_period_label_mismatch",
                    "error_message": "Required chart card has no period_label.",
                }
            )
    return errors


def _dashboard_card_row(contract: CardContract) -> dict[str, Any]:
    return {
        "country": contract.country,
        "dashboard_id": contract.dashboard_id,
        "team_id": contract.team_id,
        "tab": contract.tab,
        "tab_name": contract.tab_name,
        "card_id": contract.card_id,
        "card_title": contract.card_title,
        "card_role": contract.visual_role,
        "card_type": contract.card_type,
        "parse_strategy": contract.parse_strategy,
        "required": contract.required,
        "discovered_at": contract.discovered_at,
    }


def _read_raw_calls(store: ParquetStore, country: str) -> list[dict[str, Any]]:
    root = store.settings.parquet_dir / f"country={country}" / "raw_api_calls"
    files = sorted(root.rglob("*.parquet")) if root.exists() else []
    rows: list[dict[str, Any]] = []
    for file in files:
        rows.extend(store._read_parquet_files([file]).to_dicts())  # noqa: SLF001
    return rows


def _metadata(request_json: dict[str, Any]) -> dict[str, Any]:
    query = request_json.get("query")
    container = query if isinstance(query, dict) else request_json
    metadata = container.get("metadata") if isinstance(container, dict) else None
    return metadata if isinstance(metadata, dict) else {}


def _metric_ids(raw_value: Any, metadata_value: Any) -> list[str]:
    value = raw_value if raw_value not in (None, "", "[]") else metadata_value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
        return [str(parsed)]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _query_dimensions(request_json: dict[str, Any]) -> list[str]:
    query = request_json.get("query")
    container = query if isinstance(query, dict) else request_json
    values: set[str] = set()
    for key in ("dimensions", "dimensionFills"):
        current = container.get(key) if isinstance(container, dict) else None
        if isinstance(current, dict):
            nested = current.get(key) or current.get("dimensions") or current.get("dimensionFills")
        else:
            nested = current
        if isinstance(nested, list):
            for item in nested:
                if isinstance(item, str):
                    values.add(canonicalize_key(item))
                elif isinstance(item, dict):
                    raw = item.get("id") or item.get("key") or item.get("name")
                    if raw:
                        values.add(canonicalize_key(str(raw)))
    return sorted(values)


def _period_from_call(call: dict[str, Any]) -> dict[str, str] | None:
    start = _text(call.get("source_ts_start"))
    end = _text(call.get("source_ts_end"))
    timezone = "CST"
    request_json = parse_json_object(call.get("request_json"))
    query = request_json.get("query")
    container = query if isinstance(query, dict) else request_json
    dimension_fills = container.get("dimensionFills") if isinstance(container, dict) else None
    fills = dimension_fills.get("dimensionFills") if isinstance(dimension_fills, dict) else None
    if isinstance(fills, list):
        for item in fills:
            if not isinstance(item, dict):
                continue
            namespace = item.get("namespace")
            arguments = item.get("arguments")
            if (
                isinstance(namespace, list)
                and namespace[-1:] == ["ts"]
                and isinstance(arguments, list)
                and len(arguments) >= 2
            ):
                start = start or _text(arguments[0])
                end = end or _text(arguments[1])
                if len(arguments) >= 4:
                    timezone = _timezone_from_offset(arguments[3]) or timezone
    dimensions = container.get("dimensions") if isinstance(container, dict) else None
    dimension_items = dimensions.get("dimensions") if isinstance(dimensions, dict) else None
    if isinstance(dimension_items, list):
        for item in dimension_items:
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata")
            if not isinstance(metadata, dict):
                continue
            start = start or _text(metadata.get("baseTs"))
            end = end or _text(metadata.get("endTs"))
            timezone = _timezone_from_offset(metadata.get("utcOffset")) or timezone
    if start or end:
        return {"start": start or "", "end": end or "", "timezone": timezone}
    return None


def _timezone_from_offset(value: Any) -> str | None:
    try:
        offset = int(value)
    except (TypeError, ValueError):
        return None
    if offset == -21600:
        return "CST"
    hours = offset // 3600
    return f"UTC{hours:+03d}:00"


def _response_columns(response_json: dict[str, Any]) -> list[str]:
    columns = response_json.get("columns") or response_json.get("columnNames")
    if not isinstance(columns, list):
        return []
    parsed: list[str] = []
    for column in columns:
        if isinstance(column, str):
            parsed.append(column)
        elif isinstance(column, dict):
            value = column.get("label") or column.get("name") or column.get("key")
            if value:
                parsed.append(str(value))
    return parsed


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _period_label(start: Any, end: Any, timezone: Any) -> str | None:
    tz = _text(timezone) or "CST"
    start_dt = parse_datetime(start, tz)
    end_dt = parse_datetime(end, tz)
    if not start_dt or not end_dt:
        return None
    return format_period_label(start_dt, end_dt, tz)


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
