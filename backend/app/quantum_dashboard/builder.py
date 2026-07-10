from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from backend.app.analytics.normalizer import canonicalize_key, parse_json_object
from backend.app.quantum.schemas import QuantumWidgetConfig
from backend.app.quantum_dashboard.card_mapper import card_title_for_role
from backend.app.quantum_dashboard.catalog import (
    ERRORS_APP_COMPARISON,
    required_roles,
    spec_for_role,
)
from backend.app.quantum_dashboard.generic_roles import is_generic_role
from backend.app.quantum_dashboard.models import (
    CardContract,
    DashboardPeriod,
    DashboardTab,
    DerivedBuildResult,
    ParserResult,
    RegressionStatus,
    VisualRole,
    WebSnapshot,
)
from backend.app.quantum_dashboard.parsers import build_line_chart_payload_from_series, parse_card
from backend.app.quantum_dashboard.periods import format_period_label, parse_datetime
from backend.app.quantum_dashboard.semantics import semantic_intent, semantic_state
from backend.app.quantum_dashboard.widget_roles import (
    WidgetRoleDescriptor,
    descriptors_from_widgets,
    enrich_ambiguous_calls_with_descriptor_sequence,
    enrich_call_with_descriptor,
    resolve_call_role,
)
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
DATASET_DASHBOARD_TABS = "derived/dashboard_tabs"
DATASET_DASHBOARD_WIDGETS = "derived/dashboard_widgets"
DATASET_WIDGET_CHART_PAYLOADS = "derived/widget_chart_payloads"
DATASET_WIDGET_TABLE_PAYLOADS = "derived/widget_table_payloads"
DATASET_WIDGET_REGRESSION = "derived/widget_regression"
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


@dataclass
class RelatedRoleCalls:
    base_metric: dict[str, Any] | None = None
    comparison_metric: dict[str, Any] | None = None
    base_total_metric: dict[str, Any] | None = None
    comparison_total_metric: dict[str, Any] | None = None
    base_timeseries: dict[str, Any] | None = None
    comparison_timeseries: dict[str, Any] | None = None


def build_derived_datasets(
    store: ParquetStore,
    country: str,
    *,
    raw_calls: list[dict[str, Any]] | None = None,
    ingestion_id: str | None = None,
    enabled_roles: set[str] | list[str] | None = None,
    dashboard_id: str | None = None,
    dashboard_name: str | None = None,
    range_key: str = "today",
    widget_configs: list[QuantumWidgetConfig] | None = None,
) -> DerivedBuildResult:
    calls = raw_calls if raw_calls is not None else _read_raw_calls(store, country, range_key)
    calls = _filter_calls_for_range(calls, range_key)
    calls = _filter_calls_for_dashboard(calls, dashboard_id)
    calls = _filter_calls_to_latest_period(calls, range_key)
    enabled_role_set: set[str] = (
        set(enabled_roles)
        if enabled_roles is not None
        else {str(role) for role in required_roles()}
    )
    descriptors = descriptors_from_widgets(widget_configs)
    calls = enrich_ambiguous_calls_with_descriptor_sequence(
        calls,
        descriptors=descriptors,
        enabled_roles=enabled_role_set,
    )
    selected = _latest_call_by_role(calls, descriptors, enabled_role_set)
    selected = {role: call for role, call in selected.items() if str(role) in enabled_role_set}
    related_calls_by_role = _related_calls_by_role(calls, descriptors, enabled_role_set)
    related_calls_by_role = {
        role: calls
        for role, calls in related_calls_by_role.items()
        if str(role) in enabled_role_set
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
    dashboard_widget_rows: list[dict[str, Any]] = []
    widget_table_payload_rows: list[dict[str, Any]] = []
    parser_errors: list[dict[str, str]] = []

    for role, call in selected.items():
        contract = _contract_from_call(
            country,
            role,
            call,
            now,
            range_key=range_key,
            dashboard_id=dashboard_id,
            dashboard_name=dashboard_name,
        )
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

        result = _with_related_timeseries(
            result,
            related_calls_by_role.get(role),
            role,
            range_key=range_key,
        )

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
            dashboard_widget_rows=dashboard_widget_rows,
            widget_table_payload_rows=widget_table_payload_rows,
        )

    validation_errors = _validate_required_chart_payloads(
        selected, summary_widgets, errors_widgets, snapshots, enabled_role_set
    )
    parser_errors.extend(validation_errors)

    _write_range_dataset(
        store,
        country,
        DATASET_VISUAL_CONTRACTS,
        [contract.model_dump(mode="json") for contract in contracts],
        file_name="visual_contracts.parquet",
        range_key=range_key,
    )
    _write_range_dataset(
        store,
        country,
        DATASET_DASHBOARD_CARDS,
        [_dashboard_card_row(contract) for contract in contracts],
        file_name="dashboard_cards.parquet",
        range_key=range_key,
    )
    _write_range_dataset(
        store,
        country,
        DATASET_WEB_SNAPSHOTS,
        [snapshot.model_dump(mode="json") for snapshot in snapshots],
        file_name="web_snapshots.parquet",
        range_key=range_key,
    )
    _write_range_dataset(
        store, country, DATASET_SUMMARY_WIDGETS, summary_widgets, range_key=range_key
    )
    _write_range_dataset(store, country, DATASET_SUMMARY_TABLE, summary_rows, range_key=range_key)
    _write_range_dataset(
        store, country, DATASET_ERRORS_WIDGETS, errors_widgets, range_key=range_key
    )
    _write_range_dataset(
        store, country, DATASET_ERRORS_TOP_ERRORS, top_error_rows, range_key=range_key
    )
    _write_range_dataset(
        store, country, DATASET_ERRORS_APP_NAME, error_app_rows, range_key=range_key
    )
    _write_range_dataset(store, country, DATASET_TIMESERIES, timeseries_rows, range_key=range_key)
    _write_range_dataset(
        store, country, DATASET_CHART_PAYLOADS, chart_payload_rows, range_key=range_key
    )
    _write_range_dataset(
        store,
        country,
        DATASET_DASHBOARD_TABS,
        _dashboard_tab_rows(contracts),
        range_key=range_key,
    )
    _write_range_dataset(
        store,
        country,
        DATASET_DASHBOARD_WIDGETS,
        dashboard_widget_rows,
        range_key=range_key,
    )
    _write_range_dataset(
        store,
        country,
        DATASET_WIDGET_CHART_PAYLOADS,
        chart_payload_rows,
        range_key=range_key,
    )
    _write_range_dataset(
        store,
        country,
        DATASET_WIDGET_TABLE_PAYLOADS,
        widget_table_payload_rows,
        range_key=range_key,
    )

    expected_roles = sorted(enabled_role_set)
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
                dashboard_widget_rows,
                widget_table_payload_rows,
            )
        ),
        missing_roles=[str(role) for role in missing],
        parser_errors=parser_errors,
        regression_status=regression_status,
    )


def _latest_call_by_role(
    calls: list[dict[str, Any]],
    descriptors: list[WidgetRoleDescriptor],
    enabled_roles: set[str],
) -> dict[VisualRole, dict[str, Any]]:
    selected: dict[VisualRole, dict[str, Any]] = {}
    scores: dict[VisualRole, int] = {}
    for call in calls:
        if _is_non_widget_query(call):
            continue
        role, descriptor = resolve_call_role(
            call,
            descriptors=descriptors,
            enabled_roles=enabled_roles,
        )
        if role is None:
            continue
        enriched = enrich_call_with_descriptor(call, descriptor, role)
        score = _call_score(role, enriched)
        if role not in selected or score >= scores[role]:
            selected[role] = enriched
            scores[role] = score
    return selected


def _related_calls_by_role(
    calls: list[dict[str, Any]],
    descriptors: list[WidgetRoleDescriptor],
    enabled_roles: set[str],
) -> dict[VisualRole, RelatedRoleCalls]:
    selected: dict[VisualRole, RelatedRoleCalls] = {}
    scores: dict[tuple[VisualRole, str], int] = {}
    last_role_by_card: dict[str, VisualRole] = {}
    for call in calls:
        if _is_non_widget_query(call):
            continue
        mapped_role, descriptor = resolve_call_role(
            call,
            descriptors=descriptors,
            enabled_roles=enabled_roles,
        )
        card_id = _text(call.get("card_id"))
        view_name = str(call.get("view_name") or "")
        if mapped_role is not None and card_id:
            last_role_by_card[card_id] = mapped_role
        role = mapped_role or (last_role_by_card.get(card_id) if card_id else None)
        if role is None:
            continue
        if _response_has_error(call):
            continue
        enriched = enrich_call_with_descriptor(call, descriptor, role)
        related = selected.setdefault(role, RelatedRoleCalls())
        variant = "comparison" if "ComparisonSegment" in view_name else "base"
        if "timeSeriesQuery" in view_name:
            slot = f"{variant}_timeseries"
            score = _timeseries_score(enriched)
        elif view_name in {"coreMetrics", "coreMetricsComparisonSegment"}:
            slot = f"{variant}_total_metric"
            score = _call_score(role, enriched)
        elif ":historical" in view_name:
            continue
        else:
            slot = f"{variant}_metric"
            score = _call_score(role, enriched)
        key = (role, slot)
        if score >= scores.get(key, -1):
            setattr(related, slot, enriched)
            scores[key] = score
    return selected


def _timeseries_score(call: dict[str, Any]) -> int:
    view_name = str(call.get("view_name") or "")
    score = int(call.get("row_count") or 0)
    if "ComparisonSegment" in view_name:
        score += 200
    if ":historical" not in view_name:
        score += 100
    return score


def _is_non_widget_query(call: dict[str, Any]) -> bool:
    return str(call.get("view_name") or "") in {"navbarMetricsQuery", "dashboardReplayQuery"}


def _with_related_timeseries(
    result: ParserResult,
    related_calls: RelatedRoleCalls | None,
    role: VisualRole,
    *,
    range_key: str,
) -> ParserResult:
    if related_calls is None:
        return result
    widget = result.data.get("widget")
    if not isinstance(widget, dict):
        return result
    base_timeseries = _parsed_timeseries(related_calls.base_timeseries, role)
    comparison_timeseries = _parsed_timeseries(related_calls.comparison_timeseries, role)
    single_series = bool(base_timeseries) and not comparison_timeseries
    base_widget = _parsed_widget(related_calls.base_metric, role)
    comparison_widget = _parsed_widget(related_calls.comparison_metric, role)
    if base_widget or comparison_widget:
        breakdown = []
        if base_widget and base_widget.get("value") is not None:
            breakdown.append(
                {
                    "label": "All Users" if is_generic_role(role) or single_series else "Desktop",
                    "value": base_widget["value"],
                }
            )
        if comparison_widget and comparison_widget.get("value") is not None:
            breakdown.append(
                {
                    "label": "Historical Range" if is_generic_role(role) else "Mobile",
                    "value": comparison_widget["value"],
                }
            )
        if breakdown:
            widget["breakdown"] = breakdown
            spec = spec_for_role(role)
            unit = str(widget.get("unit") or (spec.unit if spec else None) or "count")
            if unit == "count":
                widget["value"] = round(sum(float(item["value"]) for item in breakdown), 2)
            elif comparison_widget and comparison_widget.get("value") is not None:
                widget["value"] = comparison_widget["value"]
    if role == ERRORS_APP_COMPARISON:
        total = _donut_total_from_related_metric(
            related_calls.base_total_metric or related_calls.comparison_total_metric,
            role,
        )
        if total is not None:
            widget["value"] = total
            widget["total"] = total
    period_call = (
        related_calls.comparison_timeseries
        or related_calls.base_timeseries
        or related_calls.comparison_total_metric
        or related_calls.base_total_metric
        or related_calls.comparison_metric
        or related_calls.base_metric
    )
    period = _period_from_call(period_call or {})
    if base_timeseries or comparison_timeseries:
        spec = spec_for_role(role)
        mobile_points = (
            base_timeseries if is_generic_role(role) or single_series else comparison_timeseries
        )
        desktop_points = [] if is_generic_role(role) or single_series else base_timeseries
        chart_payload = build_line_chart_payload_from_series(
            role=role,
            title=str(widget.get("title") or (spec.title if spec else role)),
            unit=str(widget.get("unit") or (spec.unit if spec else None) or "count"),
            mobile_points=mobile_points,
            desktop_points=desktop_points,
            response_json=parse_json_object(
                (related_calls.comparison_timeseries or related_calls.base_timeseries or {}).get(
                    "response_json"
                )
            ),
            aggregate_daily=range_key == "last_7_days",
            period_end=period.get("end") if period else None,
            mobile_label="All Users" if is_generic_role(role) or single_series else "Mobile",
            desktop_label="Desktop",
        )
        if isinstance(chart_payload, dict):
            widget["chart_payload"] = chart_payload
            widget["timeseries"] = _flatten_chart_series(chart_payload)
    if period:
        widget["period"] = period
    payload = widget.get("chart_payload")
    if isinstance(payload, dict) and period:
        payload["timezone"] = period.get("timezone") or payload.get("timezone")
    return ParserResult(role=result.role, status=result.status, data=result.data)


def _parsed_widget(call: dict[str, Any] | None, role: VisualRole) -> dict[str, Any] | None:
    if call is None:
        return None
    parsed = parse_card(call, role)
    widget = parsed.data.get("widget") if parsed.status == "ok" else None
    return widget if isinstance(widget, dict) else None


def _parsed_timeseries(call: dict[str, Any] | None, role: VisualRole) -> list[dict[str, Any]]:
    widget = _parsed_widget(call, role)
    if not widget:
        return []
    timeseries = widget.get("timeseries")
    return timeseries if isinstance(timeseries, list) else []


def _donut_total_from_related_metric(call: dict[str, Any] | None, role: VisualRole) -> float | None:
    widget = _parsed_widget(call, role)
    if not widget:
        return None
    total = widget.get("total") or widget.get("value")
    return _float_or_none(total)


def _flatten_chart_series(chart_payload: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    series = chart_payload.get("series")
    if not isinstance(series, list):
        return output
    for item in series:
        if not isinstance(item, dict):
            continue
        label = item.get("label")
        points = item.get("points")
        if not isinstance(points, list):
            continue
        output.extend({**point, "series": label} for point in _list_of_dicts(points))
    return output


def _call_score(role: VisualRole, call: dict[str, Any]) -> int:
    view_name = str(call.get("view_name") or "")
    score = int(call.get("row_count") or 0)
    if is_generic_role(role) and str(call.get("card_type") or "").upper() == "TABLE":
        if view_name == "table":
            score += 1000
        if view_name == "topN":
            score += 900
        if view_name == "dimensionQuery":
            score += 800
        if view_name == "coreMetrics":
            score += 100
    elif is_generic_role(role):
        if view_name == "coreMetrics":
            score += 5000
        if view_name == "coreMetricsComparisonSegment":
            score += 4500
        if view_name == "dimensionQuery":
            score += 4000
        if view_name == "dimensionQueryComparisonSegment":
            score += 3500
        if "timeSeriesQuery" in view_name:
            score += 500
        if view_name.endswith(":historical"):
            score -= 250
    elif role in {
        "summary.detail_by_app_name_os",
        "errors.top_errors_by_error_name",
        "errors.error_session_percentage_by_app_name",
        "errors.error_sessions_by_app_name_comparison",
    }:
        if view_name == "table":
            score += 1000
        if view_name == "topN":
            score += 900
        if view_name == "dimensionQuery":
            score += 800
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
    if _response_has_error(call):
        score -= 1000
    return score


def _response_has_error(call: dict[str, Any]) -> bool:
    try:
        if int(call.get("status_code") or 0) >= 400:
            return True
    except (TypeError, ValueError):
        pass
    response = parse_json_object(call.get("response_json"))
    return bool(response.get("error"))


def _contract_from_call(
    country: str,
    role: VisualRole,
    call: dict[str, Any],
    discovered_at: str,
    *,
    range_key: str,
    dashboard_id: str | None = None,
    dashboard_name: str | None = None,
) -> CardContract:
    spec = spec_for_role(role)
    if spec is None:
        raise ValueError(f"No dashboard card spec registered for role {role}.")
    request_json = parse_json_object(call.get("request_json"))
    response_json = parse_json_object(call.get("response_json"))
    metadata = _metadata(request_json)
    metric_ids = _metric_ids(call.get("metric_ids"), metadata.get("metricIds"))
    dimensions = _query_dimensions(request_json)
    period = _period_from_call(call)
    period_label = _period_label(
        period.get("start") if period else _text(call.get("range_start")),
        period.get("end") if period else _text(call.get("range_end")),
        (period.get("timezone") if period else None) or _text(call.get("range_timezone")) or "CST",
    )
    card_id = _text(call.get("card_id") or metadata.get("cardId")) or f"mapped:{role}"
    tab = _text(call.get("tab"))
    tab_name = _text(call.get("tab_name"))
    resolved_tab: DashboardTab = _safe_tab_token(tab or spec.tab)
    tab_index = _int(call.get("tab_index"), _tab_index_from_tab(resolved_tab))
    return CardContract(
        country=country,
        dashboard_id=dashboard_id or _text(call.get("dashboard_id") or metadata.get("dashboardId")),
        dashboard_name=dashboard_name or _text(call.get("dashboard_name")),
        team_id=_text(call.get("team_id") or metadata.get("teamId") or metadata.get("teamID")),
        range_key=_text(call.get("range_key")) or range_key,
        range_start=_text(call.get("range_start") or call.get("source_ts_start")),
        range_end=_text(call.get("range_end") or call.get("source_ts_end")),
        range_timezone=_text(call.get("range_timezone") or call.get("source_timezone")) or "CST",
        period_label=period_label,
        capture_mode=_text(call.get("capture_mode")) or "range_contract",
        source_query_hash=_text(call.get("query_hash")) or hash_json(request_json),
        source_response_hash=_text(call.get("response_hash")) or hash_json(response_json),
        tab=resolved_tab,
        tab_name=tab_name or _tab_label(resolved_tab),
        tab_index=tab_index,
        widget_id=_text(call.get("widget_id")) or card_id,
        widget_order=_int_or_none(call.get("widget_order")),
        card_id=card_id,
        card_title=_text(call.get("card_title")) or card_title_for_role(role, call),
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
    snapshot_hash = hash_json(
        {
            "role": contract.visual_role,
            "value": visible_value,
            "breakdowns": widget.get("breakdown") or widget.get("series"),
            "rows": rows[:10],
            "period": contract.period_label,
        }
    )
    return WebSnapshot(
        ingestion_id=str(call.get("ingestion_id") or ""),
        country=country,
        dashboard_id=contract.dashboard_id,
        dashboard_name=contract.dashboard_name,
        team_id=contract.team_id,
        range_key=contract.range_key,
        range_start=contract.range_start,
        range_end=contract.range_end,
        range_timezone=contract.range_timezone,
        period_label=contract.period_label,
        source_query_hash=contract.source_query_hash,
        source_response_hash=contract.source_response_hash,
        web_snapshot_hash=snapshot_hash,
        tab=contract.tab,
        tab_index=contract.tab_index,
        card_role=contract.visual_role,
        widget_id=contract.widget_id,
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
    dashboard_widget_rows: list[dict[str, Any]],
    widget_table_payload_rows: list[dict[str, Any]],
) -> None:
    widget = result.data.get("widget")
    rows = result.data.get("rows")
    columns = result.data.get("columns")
    if isinstance(widget, dict):
        row = _widget_row(contract, widget)
        if contract.tab == "summary":
            summary_widgets.append(row)
        else:
            errors_widgets.append(row)
        dashboard_widget_rows.append(row)
        for point in _list_of_dicts(widget.get("timeseries")):
            timeseries_rows.append(
                {
                    "country": contract.country,
                    "dashboard_id": contract.dashboard_id,
                    "dashboard_name": contract.dashboard_name,
                    "widget_id": contract.widget_id,
                    "card_id": contract.card_id,
                    "widget_type": contract.card_type,
                    "tab_name": contract.tab_name,
                    "tab_index": contract.tab_index,
                    "widget_order": contract.widget_order,
                    "range_key": contract.range_key,
                    "range_start": contract.range_start,
                    "range_end": contract.range_end,
                    "range_timezone": contract.range_timezone,
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
        table_rows = _list_of_dicts(widget.get("table_rows"))
        if widget.get("chart_type") == "table" or table_rows:
            widget_table_payload_rows.append(
                {
                    "country": contract.country,
                    "dashboard_id": contract.dashboard_id,
                    "dashboard_name": contract.dashboard_name,
                    "widget_id": contract.widget_id,
                    "card_id": contract.card_id,
                    "widget_type": contract.card_type,
                    "tab": contract.tab,
                    "tab_name": contract.tab_name,
                    "tab_index": contract.tab_index,
                    "widget_order": contract.widget_order,
                    "range_key": contract.range_key,
                    "card_role": role,
                    "card_title": contract.card_title,
                    "table_columns": widget.get("table_columns", []),
                    "table_rows": table_rows,
                    "source_query_hash": contract.source_query_hash,
                    "source_response_hash": contract.source_response_hash,
                    "period_label": contract.period_label,
                }
            )
    elif isinstance(rows, list):
        table_widget = {
            "id": contract.visual_role,
            "role": role,
            "title": contract.card_title,
            "value": len(rows),
            "unit": "count",
            "chart_type": "table",
            "breakdown": [],
            "timeseries": [],
            "table_columns": [
                str(column) for column in (columns if isinstance(columns, list) else [])
            ],
            "table_rows": _list_of_dicts(rows),
            "period": contract.period.model_dump(mode="json"),
        }
        row = _widget_row(contract, table_widget)
        dashboard_widget_rows.append(row)
        widget_table_payload_rows.append(
            {
                "country": contract.country,
                "dashboard_id": contract.dashboard_id,
                "dashboard_name": contract.dashboard_name,
                "widget_id": contract.widget_id,
                "card_id": contract.card_id,
                "widget_type": contract.card_type,
                "tab": contract.tab,
                "tab_name": contract.tab_name,
                "tab_index": contract.tab_index,
                "widget_order": contract.widget_order,
                "range_key": contract.range_key,
                "card_role": role,
                "card_title": contract.card_title,
                "table_columns": table_widget["table_columns"],
                "table_rows": table_widget["table_rows"],
                "source_query_hash": contract.source_query_hash,
                "source_response_hash": contract.source_response_hash,
                "period_label": contract.period_label,
            }
        )
    if isinstance(rows, list):
        for index, item in enumerate(_list_of_dicts(rows)):
            row = {
                **item,
                "country": contract.country,
                "dashboard_id": contract.dashboard_id,
                "dashboard_name": contract.dashboard_name,
                "widget_id": contract.widget_id,
                "card_id": contract.card_id,
                "widget_type": contract.card_type,
                "tab_name": contract.tab_name,
                "tab_index": contract.tab_index,
                "widget_order": contract.widget_order,
                "range_key": contract.range_key,
                "range_start": contract.range_start,
                "range_end": contract.range_end,
                "range_timezone": contract.range_timezone,
                "period_label": contract.period_label,
                "source_query_hash": contract.source_query_hash,
                "source_response_hash": contract.source_response_hash,
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
        y_axis = chart_payload.get("y_axis")
        if isinstance(y_axis, dict):
            y_axis["label"] = contract.card_title or y_axis.get("label")
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
        "dashboard_id": contract.dashboard_id,
        "dashboard_name": contract.dashboard_name,
        "widget_id": contract.widget_id,
        "card_id": contract.card_id,
        "widget_type": contract.card_type,
        "tab_name": contract.tab_name,
        "tab_index": contract.tab_index,
        "widget_order": contract.widget_order,
        "range_key": contract.range_key,
        "range_start": contract.range_start,
        "range_end": contract.range_end,
        "range_timezone": contract.range_timezone,
        "capture_mode": contract.capture_mode,
        "source_query_hash": contract.source_query_hash,
        "source_response_hash": contract.source_response_hash,
        "web_snapshot_hash": contract.web_snapshot_hash,
        "card_role": contract.visual_role,
        "card_title": contract.card_title,
        "id": widget.get("id"),
        "title": contract.card_title or widget.get("title"),
        "value": widget.get("value"),
        "unit": widget.get("unit"),
        "chart_type": widget.get("chart_type"),
        "total": widget.get("total"),
        "breakdown": widget.get("breakdown", []),
        "series": widget.get("series", []),
        "timeseries": widget.get("timeseries", []),
        "table_columns": widget.get("table_columns", []),
        "table_rows": widget.get("table_rows", []),
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
    y_axis = payload.get("y_axis")
    if isinstance(y_axis, dict):
        y_axis["label"] = contract.card_title or y_axis.get("label")
    payload["period_label"] = payload.get("period_label") or _period_label(
        widget_period.get("start") or contract.period.start,
        widget_period.get("end") or contract.period.end,
        widget_period.get("timezone") or contract.period.timezone,
    )
    return {
        "country": contract.country,
        "ingestion_id": "",
        "dashboard_id": contract.dashboard_id,
        "dashboard_name": contract.dashboard_name,
        "team_id": contract.team_id,
        "widget_id": contract.widget_id,
        "range_key": contract.range_key,
        "range_start": contract.range_start,
        "range_end": contract.range_end,
        "range_timezone": contract.range_timezone,
        "capture_mode": contract.capture_mode,
        "tab": contract.tab,
        "tab_name": contract.tab_name,
        "tab_index": contract.tab_index,
        "widget_order": contract.widget_order,
        "card_id": contract.card_id,
        "widget_type": contract.card_type,
        "card_role": contract.visual_role,
        "card_title": contract.card_title,
        "chart_type": payload.get("chart_type"),
        "chart_payload": payload,
        "source_query_hash": contract.request_hash,
        "source_response_hash": contract.response_hash,
        "web_snapshot_hash": contract.web_snapshot_hash,
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
    snapshots: list[WebSnapshot],
    enabled_roles: set[str],
) -> list[dict[str, str]]:
    widgets = {str(row.get("card_role")): row for row in [*summary_widgets, *errors_widgets]}
    snapshots_by_role = {str(snapshot.card_role): snapshot for snapshot in snapshots}
    errors: list[dict[str, str]] = []
    for role in REQUIRED_CHART_ROLES:
        if str(role) not in enabled_roles:
            continue
        if role not in selected:
            continue
        widget = widgets.get(role, {})
        payload = widget.get("chart_payload")
        snapshot = snapshots_by_role.get(role)
        expects_chart_payload = bool(
            _list_of_dicts(widget.get("timeseries") or widget.get("series"))
            or (snapshot.visible_series if snapshot else [])
        )
        if not expects_chart_payload and not isinstance(payload, dict):
            continue
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
        "dashboard_name": contract.dashboard_name,
        "team_id": contract.team_id,
        "widget_id": contract.widget_id,
        "range_key": contract.range_key,
        "range_start": contract.range_start,
        "range_end": contract.range_end,
        "range_timezone": contract.range_timezone,
        "capture_mode": contract.capture_mode,
        "source_query_hash": contract.source_query_hash,
        "source_response_hash": contract.source_response_hash,
        "web_snapshot_hash": contract.web_snapshot_hash,
        "tab": contract.tab,
        "tab_name": contract.tab_name,
        "tab_index": contract.tab_index,
        "widget_order": contract.widget_order,
        "card_id": contract.card_id,
        "card_title": contract.card_title,
        "card_role": contract.visual_role,
        "card_type": contract.card_type,
        "parse_strategy": contract.parse_strategy,
        "required": contract.required,
        "discovered_at": contract.discovered_at,
    }


def _dashboard_tab_rows(contracts: list[CardContract]) -> list[dict[str, Any]]:
    rows_by_key: dict[tuple[int, str], dict[str, Any]] = {}
    for contract in contracts:
        key = (int(contract.tab_index or 0), contract.tab_name)
        rows_by_key.setdefault(
            key,
            {
                "country": contract.country,
                "dashboard_id": contract.dashboard_id,
                "dashboard_name": contract.dashboard_name,
                "team_id": contract.team_id,
                "range_key": contract.range_key,
                "tab": contract.tab,
                "tab_name": contract.tab_name,
                "tab_index": contract.tab_index or 0,
            },
        )
    return [rows_by_key[key] for key in sorted(rows_by_key)]


def _safe_tab_token(value: str | None) -> str:
    text = _text(value)
    if not text:
        return "tab-0"
    return text


def _tab_label(tab: str) -> str:
    if tab == "summary":
        return "Resumen"
    if tab == "errors":
        return "Errores"
    return tab


def _tab_index_from_tab(tab: str) -> int:
    if tab == "errors":
        return 1
    if tab.startswith("tab-"):
        try:
            return int(tab.split("-", 1)[1])
        except ValueError:
            return 0
    return 0


def range_dataset_path(dataset_path: str, range_key: str | None) -> str:
    key = _safe_range_key(range_key)
    return f"range_key={key}/{dataset_path}" if key else dataset_path


def _write_range_dataset(
    store: ParquetStore,
    country: str,
    dataset_path: str,
    rows: list[dict[str, Any]],
    *,
    range_key: str,
    file_name: str = "part-000.parquet",
) -> None:
    store.write_country_dataset(
        country,
        range_dataset_path(dataset_path, range_key),
        rows,
        file_name=file_name,
    )
    if range_key == "today":
        store.write_country_dataset(country, dataset_path, rows, file_name=file_name)


def _read_raw_calls(
    store: ParquetStore, country: str, range_key: str | None
) -> list[dict[str, Any]]:
    root = store.settings.parquet_dir / f"country={country}" / "raw_api_calls"
    files = sorted(root.rglob("*.parquet")) if root.exists() else []
    rows: list[dict[str, Any]] = []
    for file in files:
        rows.extend(store._read_parquet_files([file]).to_dicts())  # noqa: SLF001
    return rows


def _filter_calls_for_range(
    calls: list[dict[str, Any]], range_key: str | None
) -> list[dict[str, Any]]:
    key = _safe_range_key(range_key)
    if not key:
        return calls
    filtered = [
        call for call in calls if _safe_range_key(_text(call.get("range_key")) or "today") == key
    ]
    return filtered


def _filter_calls_for_dashboard(
    calls: list[dict[str, Any]], dashboard_id: str | None
) -> list[dict[str, Any]]:
    if not dashboard_id:
        return calls
    return [
        call
        for call in calls
        if _text(call.get("dashboard_id")) in {dashboard_id, None}
        or _metadata(parse_json_object(call.get("request_json"))).get("dashboardId") == dashboard_id
    ]


def _filter_calls_to_latest_period(
    calls: list[dict[str, Any]],
    range_key: str | None,
) -> list[dict[str, Any]]:
    key = _safe_range_key(range_key)
    if key not in {"today", "yesterday", "last_7_days"} or not calls:
        return calls
    periods: list[tuple[datetime, str, dict[str, Any]]] = []
    for call in calls:
        start = _period_filter_start(call)
        end = _period_filter_end(call)
        parsed_end = parse_datetime(end, _text(call.get("source_timezone")) or "CST")
        if parsed_end is None:
            continue
        periods.append((parsed_end, f"{start or ''}|{end or ''}", call))
    if not periods:
        return calls
    latest_end = max(item[0] for item in periods)
    latest_keys = {period_key for end, period_key, _ in periods if end == latest_end}
    return [
        call
        for call in calls
        if f"{_period_filter_start(call) or ''}|{_period_filter_end(call) or ''}" in latest_keys
    ]


def _period_filter_start(call: dict[str, Any]) -> str | None:
    return _text(
        call.get("range_start") or call.get("capture_chunk_start") or call.get("source_ts_start")
    )


def _period_filter_end(call: dict[str, Any]) -> str | None:
    return _text(
        call.get("range_end") or call.get("capture_chunk_end") or call.get("source_ts_end")
    )


def _safe_range_key(range_key: str | None) -> str:
    raw = (range_key or "").strip().lower()
    if raw in {"today", "yesterday", "last_7_days", "custom"}:
        return raw
    return "".join(
        character if character.isalnum() or character == "_" else "_" for character in raw
    )


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
    start = _text(call.get("source_ts_start")) or _text(call.get("capture_chunk_start"))
    end = _text(call.get("source_ts_end")) or _text(call.get("capture_chunk_end"))
    timezone = _text(call.get("source_timezone")) or "CST"
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


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
