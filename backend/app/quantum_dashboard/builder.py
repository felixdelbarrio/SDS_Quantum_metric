from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from backend.app.analytics.normalizer import canonicalize_key, parse_json_object
from backend.app.quantum_dashboard.card_mapper import card_title_for_role, map_card_role
from backend.app.quantum_dashboard.catalog import MANDATORY_CARDS, ROLE_SPECS, required_roles
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
DATASET_REGRESSION_RESULTS = "regression/web_vs_local_results"
DATASET_REGRESSION_DISCREPANCIES = "regression/discrepancies"


def build_derived_datasets(
    store: ParquetStore,
    country: str,
    *,
    raw_calls: list[dict[str, Any]] | None = None,
    ingestion_id: str | None = None,
) -> DerivedBuildResult:
    calls = raw_calls if raw_calls is not None else _read_raw_calls(store, country)
    selected = _latest_call_by_role(calls)
    now = datetime.now(UTC).isoformat()
    contracts: list[CardContract] = []
    snapshots: list[WebSnapshot] = []
    summary_widgets: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    errors_widgets: list[dict[str, Any]] = []
    top_error_rows: list[dict[str, Any]] = []
    error_app_rows: list[dict[str, Any]] = []
    timeseries_rows: list[dict[str, Any]] = []
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
        )

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

    missing = [role for role in required_roles() if role not in selected]
    mandatory_captured = len([role for role in required_roles() if role in selected])
    regression_status: RegressionStatus = (
        "passed" if not missing and not parser_errors else "failed_missing_card"
    )
    if parser_errors:
        regression_status = "failed_parse_error"

    return DerivedBuildResult(
        ingestion_id=ingestion_id,
        country=country,
        raw_calls=len(calls),
        raw_rows=sum(int(call.get("row_count") or 0) for call in calls),
        captured_cards=len(selected),
        mandatory_cards=len(MANDATORY_CARDS),
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
            start=_text(call.get("source_ts_start")),
            end=_text(call.get("source_ts_end")),
            timezone=_text(metadata.get("timezone")) or "CST",
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
        "comparison": widget.get("comparison"),
        "period_start": contract.period.start,
        "period_end": contract.period.end,
        "regression_source": "web_snapshot",
    }


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


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
