from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from backend.app.analytics.normalizer import canonicalize_key, parse_json_object
from backend.app.quantum.schemas import QuantumWidgetConfig
from backend.app.quantum_dashboard.card_mapper import card_title_for_role
from backend.app.quantum_dashboard.catalog import (
    required_roles,
    spec_for_role,
)
from backend.app.quantum_dashboard.contracts import (
    PARSE_STATUSES,
    ChartLegendContract,
    DisplayNumberContract,
    DisplayUnit,
    HistoricalComparisonContract,
    QuantumBandContract,
    QuantumBreakdownContract,
    QuantumChartContract,
    QuantumSeriesContract,
    QuantumTableColumnContract,
    QuantumTableContract,
    QuantumWidgetContract,
    SemanticIntent,
)
from backend.app.quantum_dashboard.correlation import correlate_call_to_widget
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
from backend.app.quantum_dashboard.parsers import (
    chart_payload_from_contract,
    parse_card,
    resolve_chart_contract,
)
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
DATASET_WIDGET_CONTRACTS = "derived/widget_contracts"
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

EXACT_TABLE_COLUMN_CONTRACTS: dict[str, dict[str, tuple[str, str]]] = {
    "summary.detail_by_app_name_os": {
        "name": ("name", "text"),
        "app_name": ("App Name", "text"),
        "operating_system": ("Sistema operativo", "text"),
        "page_views": ("Page Views", "number"),
        "sessions": ("Sessions", "number"),
        "conversions": ("General - Conversiones", "number"),
    },
    "errors.top_errors_by_error_name": {
        "name": ("Error Name", "text"),
        "error_sessions": ("General - Sesiones con error", "number"),
        "error_session_percent": ("General - % Sesiones con error", "percent"),
    },
    "errors.error_session_percentage_by_app_name": {
        "name": ("App Name", "text"),
        "sessions": ("Sessions", "number"),
        "sessions_with_error": ("Sessions with Error", "number"),
        "error_session_percent": ("General - % Sesiones con Error", "percent"),
    },
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
    widget_contract_rows: list[dict[str, Any]] = []
    parser_errors: list[dict[str, str]] = _correlation_errors(
        calls,
        descriptors,
        enabled_role_set,
        selected,
    )

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
            widget_contract_rows.append(
                _canonical_widget_contract(contract, result, call).storage_row()
            )
            parser_errors.append(
                {
                    "card_role": role,
                    "card_title": contract.card_title,
                    "error_code": result.error_code or "parse_error",
                    "error_message": result.error_message or "Parser failed.",
                }
            )
            continue

        result = _with_related_chart(
            result,
            related_calls_by_role.get(role),
        )

        canonical_contract = _canonical_widget_contract(contract, result, call)
        widget_contract_rows.append(canonical_contract.storage_row())

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
        selected,
        summary_widgets,
        errors_widgets,
        enabled_role_set,
        descriptors,
    )
    parser_errors.extend(validation_errors)

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
    publishable = not missing and not parser_errors
    if publishable:
        _publish_derived_datasets(
            store=store,
            country=country,
            range_key=range_key,
            contracts=contracts,
            snapshots=snapshots,
            widget_contract_rows=widget_contract_rows,
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

    return DerivedBuildResult(
        ingestion_id=ingestion_id,
        country=country,
        raw_calls=len(calls),
        raw_rows=sum(int(call.get("row_count") or 0) for call in calls),
        captured_cards=len(selected),
        mandatory_cards=len(expected_roles),
        mandatory_cards_captured=mandatory_captured,
        derived_datasets=(
            sum(
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
                    widget_contract_rows,
                )
            )
            if publishable
            else 0
        ),
        missing_roles=[str(role) for role in missing],
        parser_errors=parser_errors,
        regression_status=regression_status,
        published=publishable,
    )


def _publish_derived_datasets(
    *,
    store: ParquetStore,
    country: str,
    range_key: str,
    contracts: list[CardContract],
    snapshots: list[WebSnapshot],
    widget_contract_rows: list[dict[str, Any]],
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
    datasets = (
        (
            DATASET_VISUAL_CONTRACTS,
            [item.model_dump(mode="json") for item in contracts],
            "visual_contracts.parquet",
        ),
        (DATASET_WIDGET_CONTRACTS, widget_contract_rows, None),
        (
            DATASET_DASHBOARD_CARDS,
            [_dashboard_card_row(item) for item in contracts],
            "dashboard_cards.parquet",
        ),
        (
            DATASET_WEB_SNAPSHOTS,
            [item.model_dump(mode="json") for item in snapshots],
            "web_snapshots.parquet",
        ),
        (DATASET_SUMMARY_WIDGETS, summary_widgets, None),
        (DATASET_SUMMARY_TABLE, summary_rows, None),
        (DATASET_ERRORS_WIDGETS, errors_widgets, None),
        (DATASET_ERRORS_TOP_ERRORS, top_error_rows, None),
        (DATASET_ERRORS_APP_NAME, error_app_rows, None),
        (DATASET_TIMESERIES, timeseries_rows, None),
        (DATASET_CHART_PAYLOADS, chart_payload_rows, None),
        (DATASET_DASHBOARD_TABS, _dashboard_tab_rows(contracts), None),
        (DATASET_DASHBOARD_WIDGETS, dashboard_widget_rows, None),
        (DATASET_WIDGET_CHART_PAYLOADS, chart_payload_rows, None),
        (DATASET_WIDGET_TABLE_PAYLOADS, widget_table_payload_rows, None),
    )
    for dataset, rows, file_name in datasets:
        if file_name:
            _write_range_dataset(
                store,
                country,
                dataset,
                rows,
                file_name=file_name,
                range_key=range_key,
            )
        else:
            _write_range_dataset(
                store,
                country,
                dataset,
                rows,
                range_key=range_key,
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


def _correlation_errors(
    calls: list[dict[str, Any]],
    descriptors: list[WidgetRoleDescriptor],
    enabled_roles: set[str],
    selected: dict[VisualRole, dict[str, Any]],
) -> list[dict[str, str]]:
    if not descriptors:
        return []
    errors: dict[tuple[str, str], dict[str, str]] = {}
    active_descriptors = [item for item in descriptors if item.role in enabled_roles]
    selected_roles = {str(role) for role in selected}
    for call in calls:
        result = correlate_call_to_widget(call, active_descriptors)
        if result.status != "ambiguous":
            continue
        candidate_ids = {candidate.widget_id for candidate in result.candidates}
        candidate_descriptors = [
            descriptor
            for descriptor in active_descriptors
            if (descriptor.widget_id or descriptor.role) in candidate_ids
        ]
        candidate_roles = {descriptor.role for descriptor in candidate_descriptors}
        if candidate_roles and candidate_roles.issubset(selected_roles):
            continue
        if (
            candidate_descriptors
            and all(descriptor.widget_type == "TABLE" for descriptor in candidate_descriptors)
            and str(call.get("view_name") or "") not in {"table", "topN", "dimensionQuery"}
        ):
            continue
        card_id = _text(call.get("card_id")) or "unknown"
        key = (card_id, str(call.get("view_name") or "unknown"))
        errors[key] = {
            "card_role": "unresolved",
            "card_title": _text(call.get("card_title")) or card_id,
            "error_code": "failed_ambiguous_widget_correlation",
            "error_message": (
                "Request matches multiple widget contracts with the same strong identifiers."
            ),
        }
    return list(errors.values())


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


def _with_related_chart(
    result: ParserResult,
    related_calls: RelatedRoleCalls | None,
) -> ParserResult:
    if related_calls is None:
        return result
    widget = result.data.get("widget")
    if not isinstance(widget, dict):
        return result
    chart_payload = _explicit_chart_payload(related_calls.base_timeseries)
    if chart_payload is None:
        chart_payload = _explicit_chart_payload(related_calls.comparison_timeseries)
    if chart_payload is not None:
        widget["chart_payload"] = chart_payload
    return ParserResult(role=result.role, status=result.status, data=result.data)


def _explicit_chart_payload(call: dict[str, Any] | None) -> dict[str, Any] | None:
    if call is None:
        return None
    response_json = parse_json_object(call.get("response_json"))
    resolution = resolve_chart_contract(call, response_json)
    if resolution.status != "resolved" or not isinstance(resolution.value, QuantumChartContract):
        return None
    payload = chart_payload_from_contract(resolution.value)
    return payload if any(series.get("points") for series in payload["series"]) else None


def _call_score(role: VisualRole, call: dict[str, Any]) -> int:
    view_name = str(call.get("view_name") or "")
    score = int(call.get("row_count") or 0)
    if is_generic_role(role) and str(call.get("card_type") or "").upper() == "TABLE":
        visual_contract = parse_json_object(call.get("visual_contract"))
        table_contract = visual_contract.get("table")
        if isinstance(table_contract, dict) and table_contract.get("columns"):
            score += 10_000 + len(table_contract.get("rows") or [])
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


def _canonical_widget_contract(
    contract: CardContract,
    result: ParserResult,
    call: dict[str, Any],
) -> QuantumWidgetContract:
    widget_value = result.data.get("widget")
    widget: dict[str, Any] = widget_value if isinstance(widget_value, dict) else {}
    display = _canonical_display(widget)
    breakdown = _canonical_breakdown(widget)
    comparison = _canonical_comparison(widget)
    chart = _canonical_chart(widget)
    table = _canonical_table(widget, result.data, contract, call)
    explicit_period_label = _text(
        (chart.period_label if chart else None)
        or (table.period_label if table else None)
        or call.get("period_label")
        or contract.period_label
    )
    timezone = (
        _text(
            (chart.timezone if chart else None)
            or (table.timezone if table else None)
            or call.get("range_timezone")
            or call.get("source_timezone")
            or contract.period.timezone
        )
        or "UTC"
    )
    parse_status = "resolved"
    if (display is None and table is None and chart is None) or not explicit_period_label:
        parse_status = "failed_invalid_contract"
    if result.status != "ok":
        parse_status = (
            result.error_code if result.error_code in PARSE_STATUSES else "failed_invalid_contract"
        )
    requested_start = _text(call.get("requested_start") or contract.range_start) or ""
    requested_end = _text(call.get("requested_end") or contract.range_end) or ""
    effective_start = (
        _text(call.get("effective_start") or contract.period.start or contract.range_start) or ""
    )
    effective_end = (
        _text(call.get("effective_end") or contract.period.end or contract.range_end) or ""
    )
    return QuantumWidgetContract(
        country=contract.country,
        dashboard_id=contract.dashboard_id or "",
        dashboard_name=contract.dashboard_name or "",
        tab_id=_text(call.get("tab_id")),
        tab_name=contract.tab_name,
        tab_index=contract.tab_index or 0,
        section_id=_text(call.get("section_id")),
        section_name=_text(call.get("section_name")),
        section_index=_int_or_none(call.get("section_index")),
        widget_id=contract.widget_id or contract.card_id,
        card_id=contract.card_id,
        visual_role=contract.visual_role,
        widget_title=contract.card_title,
        widget_type=contract.card_type,
        widget_order=contract.widget_order or 0,
        layout_x=_int_or_none(call.get("layout_x")),
        layout_y=_int_or_none(call.get("layout_y")),
        layout_width=_positive_int_or_none(call.get("layout_width")),
        layout_height=_positive_int_or_none(call.get("layout_height")),
        value=display,
        breakdown=breakdown,
        comparison=comparison,
        chart=chart,
        table=table,
        range_key=contract.range_key,
        requested_start=requested_start,
        requested_end=requested_end,
        effective_start=effective_start,
        effective_end=effective_end,
        period_label=explicit_period_label or "",
        timezone=timezone,
        query_period=_text(call.get("query_period")),
        request_hash=contract.request_hash,
        response_hash=contract.response_hash,
        query_hash=contract.source_query_hash,
        parser_version="exact-widget-contract-v1",
        parse_status=cast(Any, parse_status),
    )


def _canonical_display(widget: dict[str, Any]) -> DisplayNumberContract | None:
    value = widget.get("display")
    if isinstance(value, dict):
        return DisplayNumberContract.model_validate(value)
    numeric = _float_or_none(widget.get("value"))
    if numeric is None:
        return None
    raw_unit = str(widget.get("unit") or "count")
    unit: DisplayUnit = cast(
        DisplayUnit,
        raw_unit if raw_unit in {"count", "score", "percent", "seconds", "text"} else "count",
    )
    return DisplayNumberContract(
        raw_value=numeric,
        display_value=numeric,
        unit=unit,
        precision=_decimal_places(numeric),
    )


def _canonical_breakdown(widget: dict[str, Any]) -> list[QuantumBreakdownContract]:
    values: list[QuantumBreakdownContract] = []
    for item in _list_of_dicts(widget.get("breakdown")):
        label = _text(item.get("label"))
        raw_display = item.get("display")
        if not label or not isinstance(raw_display, dict):
            continue
        display = DisplayNumberContract.model_validate(raw_display)
        values.append(
            QuantumBreakdownContract(
                label=label,
                value=display.display_value,
                display=display,
            )
        )
    return values


def _canonical_comparison(widget: dict[str, Any]) -> HistoricalComparisonContract | None:
    value = widget.get("comparison")
    if not isinstance(value, dict):
        return None
    if "display_delta" in value or "raw_delta" in value:
        return HistoricalComparisonContract.model_validate(value)
    delta = _float_or_none(value.get("delta_percent") or value.get("delta"))
    label = _text(value.get("label"))
    if delta is None or not label:
        return None
    raw_intent = str(value.get("semantic_intent") or "neutral")
    intent: SemanticIntent = cast(
        SemanticIntent,
        raw_intent if raw_intent in {"positive", "negative", "neutral"} else "neutral",
    )
    return HistoricalComparisonContract(
        label=label,
        raw_delta=delta,
        display_delta=delta,
        precision=_decimal_places(delta),
        formatted=_text(value.get("formatted")),
        semantic_intent=intent,
    )


def _canonical_chart(widget: dict[str, Any]) -> QuantumChartContract | None:
    payload = widget.get("chart_payload")
    if not isinstance(payload, dict):
        return None
    raw_type = str(payload.get("chart_type") or "").lower()
    if raw_type not in {"line", "bar", "area", "stacked_bar", "donut", "mixed"}:
        return None
    series: list[QuantumSeriesContract] = []
    for index, item in enumerate(_list_of_dicts(payload.get("series"))):
        raw_kind = str(item.get("kind") or "").lower()
        if raw_kind not in {"line", "bar", "area", "baseline", "band", "anomaly"}:
            continue
        series.append(
            QuantumSeriesContract.model_validate(
                {
                    "series_id": item.get("series_id") or item.get("id") or f"series-{index}",
                    "label": item.get("label") or item.get("name") or "",
                    "kind": raw_kind,
                    "order": item.get("order", index),
                    "points": item.get("points") or [],
                    "visible": item.get("visible") is not False,
                    "style": item.get("style"),
                }
            )
        )
    bands: list[QuantumBandContract] = []
    for index, item in enumerate(_list_of_dicts(payload.get("bands"))):
        raw_kind = str(item.get("kind") or item.get("purpose") or "custom").lower()
        if raw_kind not in {"historical_range", "anomaly", "confidence", "custom"}:
            raw_kind = "custom"
        bands.append(
            QuantumBandContract.model_validate(
                {
                    "band_id": item.get("band_id") or item.get("id") or f"band-{index}",
                    "label": item.get("label") or raw_kind.replace("_", " "),
                    "kind": raw_kind,
                    "start": item.get("start") or item.get("start_ts"),
                    "end": item.get("end") or item.get("end_ts"),
                    "lower_points": item.get("lower_points") or [],
                    "upper_points": item.get("upper_points") or [],
                    "pattern": item.get("pattern"),
                }
            )
        )
    legends = [
        ChartLegendContract.model_validate(
            {
                "id": item.get("id") or f"legend-{index}",
                "label": item.get("label") or item.get("id") or "",
                "order": item.get("order", index),
                "kind": item.get("kind"),
                "visible": item.get("visible") is not False,
            }
        )
        for index, item in enumerate(_list_of_dicts(payload.get("legends")))
    ]
    return QuantumChartContract.model_validate(
        {
            "chart_type": raw_type,
            "x_axis": payload.get("x_axis") or {"ticks": []},
            "y_axis": payload.get("y_axis") or {"ticks": []},
            "series": series,
            "bands": bands,
            "legends": legends,
            "period_label": payload.get("period_label") or "",
            "timezone": payload.get("timezone") or "UTC",
            "granularity": payload.get("granularity") or "captured",
        }
    )


def _canonical_table(
    widget: dict[str, Any],
    result_data: dict[str, Any],
    contract: CardContract,
    call: dict[str, Any],
) -> QuantumTableContract | None:
    explicit = widget.get("table_contract")
    if isinstance(explicit, dict):
        return QuantumTableContract.model_validate(explicit)
    columns: list[QuantumTableColumnContract] = []
    raw_columns = widget.get("table_columns") or result_data.get("columns")
    for item in raw_columns if isinstance(raw_columns, list) else []:
        if isinstance(item, dict):
            columns.append(QuantumTableColumnContract.model_validate(item))
        elif isinstance(item, str):
            exact = EXACT_TABLE_COLUMN_CONTRACTS.get(contract.visual_role, {}).get(item)
            if exact:
                label, data_type = exact
                columns.append(
                    QuantumTableColumnContract(
                        key=item,
                        label=label,
                        data_type=cast(Any, data_type),
                        precision=2 if data_type == "percent" else None,
                        sortable=True,
                    )
                )
    rows = _list_of_dicts(widget.get("table_rows") or result_data.get("rows"))
    if not columns:
        return None
    return QuantumTableContract(
        columns=columns,
        rows=rows,
        period_label=_text(call.get("period_label") or contract.period_label) or "",
        timezone=_text(call.get("range_timezone") or contract.period.timezone) or "UTC",
    )


def _positive_int_or_none(value: Any) -> int | None:
    parsed = _int_or_none(value)
    return parsed if parsed is not None and parsed > 0 else None


def _decimal_places(value: float) -> int:
    text = format(value, ".12f").rstrip("0").rstrip(".")
    return len(text.rsplit(".", 1)[1]) if "." in text else 0


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
    enabled_roles: set[str],
    descriptors: list[WidgetRoleDescriptor],
) -> list[dict[str, str]]:
    widgets = {str(row.get("card_role")): row for row in [*summary_widgets, *errors_widgets]}
    errors: list[dict[str, str]] = []
    required_chart_roles = {
        str(role) for role in REQUIRED_CHART_ROLES if str(role) in enabled_roles
    }
    required_chart_roles.update(
        descriptor.role
        for descriptor in descriptors
        if descriptor.role in enabled_roles and _descriptor_requires_chart(descriptor)
    )
    for role in sorted(required_chart_roles):
        if str(role) not in enabled_roles:
            continue
        if role not in selected:
            continue
        widget = widgets.get(role, {})
        raw_payload = widget.get("chart_payload")
        payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}
        series = payload.get("series")
        populated_series = [
            item
            for item in series or []
            if isinstance(item, dict) and _list_of_dicts(item.get("points"))
        ]
        if not populated_series:
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


def _descriptor_requires_chart(descriptor: WidgetRoleDescriptor) -> bool:
    if descriptor.widget_type == "DONUT":
        return True
    if descriptor.widget_type != "CHART":
        return False
    if isinstance(descriptor.visual_contract.get("chart"), dict):
        return True
    return bool(descriptor.layout_height and descriptor.layout_height >= 12)


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
