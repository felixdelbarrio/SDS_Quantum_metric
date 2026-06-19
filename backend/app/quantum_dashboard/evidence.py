from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from backend.app.quantum_dashboard.builder import (
    DATASET_ERRORS_APP_NAME,
    DATASET_ERRORS_TOP_ERRORS,
    DATASET_ERRORS_WIDGETS,
    DATASET_SUMMARY_TABLE,
    DATASET_SUMMARY_WIDGETS,
    DATASET_VISUAL_CONTRACTS,
    DATASET_WEB_SNAPSHOTS,
    range_dataset_path,
)
from backend.app.quantum_dashboard.catalog import MANDATORY_CARDS
from backend.app.storage.parquet_store import ParquetStore

type EvidenceStatus = Literal[
    "matched",
    "diverged_parser",
    "diverged_aggregation",
    "diverged_local_api",
    "missing_web_snapshot",
    "missing_contract",
    "missing_derived",
]


class WidgetEvidence(BaseModel):
    range_key: str = "today"
    role: str
    web_visible_value: float | str | None = None
    web_period_label: str | None = None
    quantum_endpoint: str | None = None
    quantum_response_path: str | None = None
    raw_query_hash: str | None = None
    raw_response_hash: str | None = None
    web_snapshot_hash: str | None = None
    parquet_path: str | None = None
    derived_path: str | None = None
    local_api_value: float | str | None = None
    status: EvidenceStatus
    first_divergence: str | None = None


def build_evidence_report(
    store: ParquetStore,
    country: str,
    *,
    roles: set[str] | list[str] | None = None,
    range_key: str = "today",
) -> list[WidgetEvidence]:
    expected_roles = set(roles) if roles is not None else {spec.role for spec in MANDATORY_CARDS}
    contracts = {
        str(row.get("visual_role")): row
        for row in _read_dataset(store, country, DATASET_VISUAL_CONTRACTS, range_key)
    }
    snapshots = {
        str(row.get("card_role")): row
        for row in _read_dataset(store, country, DATASET_WEB_SNAPSHOTS, range_key)
    }
    evidence: list[WidgetEvidence] = []
    for role in sorted(expected_roles):
        contract = contracts.get(role)
        snapshot = snapshots.get(role)
        local = _local_payload(store, country, role, range_key)
        status, first_divergence = _status(snapshot, local, contract)
        evidence.append(
            WidgetEvidence(
                range_key=range_key,
                role=role,
                web_visible_value=_web_value(snapshot),
                web_period_label=_text(snapshot.get("period_label")) if snapshot else None,
                quantum_endpoint=_text(contract.get("source_endpoint")) if contract else None,
                quantum_response_path=f"country={country}/raw_api_calls" if contract else None,
                raw_query_hash=_text(contract.get("request_hash")) if contract else None,
                raw_response_hash=_text(contract.get("response_hash")) if contract else None,
                web_snapshot_hash=_text(snapshot.get("web_snapshot_hash")) if snapshot else None,
                parquet_path=f"parquet/country={country}/raw_api_calls",
                derived_path=_derived_path(role) if local else None,
                local_api_value=_local_value(local),
                status=status,
                first_divergence=first_divergence,
            )
        )
    return evidence


def _status(
    snapshot: dict[str, Any] | None,
    local: dict[str, Any] | None,
    contract: dict[str, Any] | None,
) -> tuple[EvidenceStatus, str | None]:
    if contract is None:
        return "missing_contract", "Quantum response parseada -> visual contract"
    if snapshot is None:
        return "missing_web_snapshot", "Quantum response parseada -> web snapshot"
    if local is None:
        return "missing_derived", "Parquet raw -> derived"
    web = _web_value(snapshot)
    local_value = _local_value(local)
    if _normalized(web) == _normalized(local_value):
        return "matched", None
    return "diverged_aggregation", "Derived -> Local API"


def _local_payload(
    store: ParquetStore,
    country: str,
    role: str,
    range_key: str,
) -> dict[str, Any] | None:
    if role.startswith("summary.") and role != "summary.detail_by_app_name_os":
        return _first_role(_read_dataset(store, country, DATASET_SUMMARY_WIDGETS, range_key), role)
    if role == "summary.detail_by_app_name_os":
        rows = [
            row
            for row in _read_dataset(store, country, DATASET_SUMMARY_TABLE, range_key)
            if row.get("card_role") == role
        ]
        return {"rows": rows} if rows else None
    if role in {
        "errors.error_sessions_percentage_evolution",
        "errors.error_sessions_by_app_name_comparison",
    }:
        return _first_role(_read_dataset(store, country, DATASET_ERRORS_WIDGETS, range_key), role)
    if role == "errors.top_errors_by_error_name":
        rows = [
            row
            for row in _read_dataset(store, country, DATASET_ERRORS_TOP_ERRORS, range_key)
            if row.get("card_role") == role
        ]
        return {"rows": rows} if rows else None
    if role == "errors.error_session_percentage_by_app_name":
        rows = [
            row
            for row in _read_dataset(store, country, DATASET_ERRORS_APP_NAME, range_key)
            if row.get("card_role") == role
        ]
        return {"rows": rows} if rows else None
    return None


def _first_role(rows: list[dict[str, Any]], role: str) -> dict[str, Any] | None:
    return next((row for row in rows if row.get("card_role") == role), None)


def _web_value(snapshot: dict[str, Any] | None) -> float | str | None:
    if not snapshot:
        return None
    value = snapshot.get("visible_value")
    if value is not None:
        return value if isinstance(value, (int, float, str)) else str(value)
    rows = snapshot.get("visible_table_rows")
    return len(rows) if isinstance(rows, list) else None


def _local_value(local: dict[str, Any] | None) -> float | str | None:
    if not local:
        return None
    for key in ("value", "total"):
        if local.get(key) is not None:
            value = local.get(key)
            return value if isinstance(value, (int, float, str)) else str(value)
    rows = local.get("rows")
    return len(rows) if isinstance(rows, list) else None


def _derived_path(role: str) -> str:
    if role.startswith("summary.") and role != "summary.detail_by_app_name_os":
        return DATASET_SUMMARY_WIDGETS
    if role == "summary.detail_by_app_name_os":
        return DATASET_SUMMARY_TABLE
    if role in {
        "errors.error_sessions_percentage_evolution",
        "errors.error_sessions_by_app_name_comparison",
    }:
        return DATASET_ERRORS_WIDGETS
    if role == "errors.top_errors_by_error_name":
        return DATASET_ERRORS_TOP_ERRORS
    if role == "errors.error_session_percentage_by_app_name":
        return DATASET_ERRORS_APP_NAME
    return "derived/unknown"


def _normalized(value: object) -> object:
    if isinstance(value, str):
        text = value.replace(",", "").replace("%", "").strip()
        try:
            return round(float(text), 6)
        except ValueError:
            return text
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(float(value), 6)
    return value


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _read_dataset(
    store: ParquetStore,
    country: str,
    dataset_path: str,
    range_key: str,
) -> list[dict[str, Any]]:
    rows = store.read_country_dataset(country, range_dataset_path(dataset_path, range_key))
    if not rows and range_key == "today":
        return store.read_country_dataset(country, dataset_path)
    return rows
