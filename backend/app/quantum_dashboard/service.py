from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import polars as pl

from backend.app.analytics.models import TableColumn
from backend.app.quantum.schemas import COUNTRY_LABELS, COUNTRY_ORDER, Country
from backend.app.quantum_dashboard.builder import (
    DATASET_ERRORS_APP_NAME,
    DATASET_ERRORS_TOP_ERRORS,
    DATASET_ERRORS_WIDGETS,
    DATASET_REGRESSION_RESULTS,
    DATASET_SUMMARY_TABLE,
    DATASET_SUMMARY_WIDGETS,
    DATASET_VISUAL_CONTRACTS,
)
from backend.app.quantum_dashboard.catalog import MANDATORY_CARDS, required_roles
from backend.app.quantum_dashboard.models import DashboardTab
from backend.app.storage.parquet_store import ParquetStore

SUMMARY_COLUMNS = [
    TableColumn(key="name", label="name", sortable=True),
    TableColumn(key="app_name", label="App Name", sortable=True),
    TableColumn(key="operating_system", label="Sistema operativo", sortable=True),
    TableColumn(key="page_views", label="Page Views", sortable=True),
    TableColumn(key="sessions", label="Sessions", sortable=True),
    TableColumn(key="conversions", label="General - Conversiones", sortable=True),
]

TOP_ERRORS_COLUMNS = [
    TableColumn(key="name", label="Error Name", sortable=True),
    TableColumn(key="error_sessions", label="General - Sesiones con error", sortable=True),
    TableColumn(
        key="error_session_percent",
        label="General - % Sesiones con error",
        sortable=True,
    ),
]

ERROR_APP_COLUMNS = [
    TableColumn(key="name", label="App Name", sortable=True),
    TableColumn(key="sessions", label="Sessions", sortable=True),
    TableColumn(key="sessions_with_error", label="Sessions with Error", sortable=True),
    TableColumn(
        key="error_session_percent",
        label="General - % Sesiones con Error",
        sortable=True,
    ),
]


class LocalDashboardService:
    def __init__(self, store: ParquetStore) -> None:
        self.store = store

    def countries(self) -> dict[str, Any]:
        countries = []
        first_ready: str | None = None
        for country in COUNTRY_ORDER:
            status = self.status(country.value)
            if not status["has_data"]:
                continue
            if first_ready is None:
                first_ready = country.value
            countries.append(
                {
                    "code": country.value,
                    "label": COUNTRY_LABELS[country.value],
                    "has_data": status["has_data"],
                    "raw_calls": status["calls"],
                    "rows": status["rows"],
                    "cards": status["cards"],
                    "regression_status": status["regression_status"],
                    "last_ingestion_at": status["last_ingestion_at"],
                }
            )
        configured = str(self.store.settings.qm_country or Country.MX.value)
        return {"countries": countries, "default_country": first_ready or configured}

    def status(self, country: str) -> dict[str, Any]:
        raw_calls = self._raw_calls(country)
        contracts = self.store.read_country_dataset(country, DATASET_VISUAL_CONTRACTS)
        contract_roles = {str(row.get("visual_role")) for row in contracts}
        regression = self._latest_regression(country)
        summary_ready = self._tab_ready("summary", contract_roles) and (
            self.store.country_dataset_exists(country, DATASET_SUMMARY_WIDGETS)
            and self.store.country_dataset_exists(country, DATASET_SUMMARY_TABLE)
        )
        errors_ready = self._tab_ready("errors", contract_roles) and (
            self.store.country_dataset_exists(country, DATASET_ERRORS_WIDGETS)
            and self.store.country_dataset_exists(country, DATASET_ERRORS_TOP_ERRORS)
            and self.store.country_dataset_exists(country, DATASET_ERRORS_APP_NAME)
        )
        missing_roles = [role for role in required_roles() if role not in contract_roles]
        reason = None
        if raw_calls and missing_roles:
            reason = (
                "Quantum responses were captured but mandatory card roles were not mapped: "
                + ", ".join(missing_roles)
            )
        elif raw_calls and not (summary_ready and errors_ready):
            reason = (
                "Datos raw disponibles, pero no existe dataset analitico derivado completo. "
                "Ejecuta regenerar derivados o una nueva ingesta."
            )
        return {
            "country": country,
            "has_data": bool(raw_calls or contracts),
            "last_ingestion_id": self._last_ingestion(country, "ingestion_id"),
            "last_ingestion_at": self._last_ingestion(country, "started_at"),
            "regression_status": regression.get("status") or "failed_missing_card",
            "regression_verdict": regression.get("verdict"),
            "calls": len(raw_calls),
            "rows": sum(int(row.get("row_count") or 0) for row in raw_calls),
            "cards": len(contract_roles),
            "captured_cards": len(contract_roles),
            "mandatory_cards": len(MANDATORY_CARDS),
            "mandatory_cards_captured": len(required_roles()) - len(missing_roles),
            "summary_ready": summary_ready,
            "errors_ready": errors_ready,
            "derived_datasets": self._derived_dataset_count(country),
            "reason": reason,
            "missing_roles": missing_roles,
            "regression_report": "docs/regression/latest-web-vs-local.md" if regression else None,
        }

    def summary(self, country: str) -> dict[str, Any]:
        status = self.status(country)
        if not status["summary_ready"] or not _regression_usable(status["regression_status"]):
            return self._empty_response(country, status, required_dataset="derived/summary")
        widgets = [
            _widget_from_row(row)
            for row in self.store.read_country_dataset(country, DATASET_SUMMARY_WIDGETS)
        ]
        order = {card.local_id: index for index, card in enumerate(MANDATORY_CARDS)}
        widgets.sort(key=lambda item: order.get(str(item["id"]), 99))
        return {
            "status": "ok",
            "country": country,
            "source": "parquet",
            "last_ingestion_at": status["last_ingestion_at"],
            "dashboard_title": f"Dashboard General {country}",
            "description": "Este dashboard es un resumen de sesiones y errores.",
            "widgets": widgets,
            "period": self._period(country),
            "regression": self._regression_metadata(status),
            "available_datasets": self._available_dataset_names(country),
        }

    def summary_table(
        self,
        country: str,
        *,
        search: str | None = None,
        sort: str = "page_views",
        direction: Literal["asc", "desc"] = "desc",
    ) -> dict[str, Any]:
        status = self.status(country)
        if not status["summary_ready"] or not _regression_usable(status["regression_status"]):
            return self._empty_table(
                country, SUMMARY_COLUMNS, status, "derived/summary_detail_table"
            )
        rows = self.store.read_country_dataset(country, DATASET_SUMMARY_TABLE)
        rows = _filter_rows(rows, search, ("name", "app_name", "operating_system"))
        rows = _sort_rows(
            rows, sort, direction, {column.key for column in SUMMARY_COLUMNS}, "page_views"
        )
        return {
            "status": "ok" if rows else "empty",
            "country": country,
            "columns": [column.model_dump(mode="json") for column in SUMMARY_COLUMNS],
            "rows": rows,
            "source": "parquet",
            "reason": None if rows else "No local summary rows match the selected filters.",
            "available_datasets": self._available_dataset_names(country),
        }

    def errors(self, country: str) -> dict[str, Any]:
        status = self.status(country)
        if not status["errors_ready"] or not _regression_usable(status["regression_status"]):
            return self._empty_response(country, status, required_dataset="derived/errors")
        widgets = [
            _widget_from_row(row)
            for row in self.store.read_country_dataset(country, DATASET_ERRORS_WIDGETS)
        ]
        return {
            "status": "ok",
            "country": country,
            "source": "parquet",
            "last_ingestion_at": status["last_ingestion_at"],
            "widgets": widgets,
            "period": self._period(country),
            "regression": self._regression_metadata(status),
            "available_datasets": self._available_dataset_names(country),
        }

    def top_errors_table(
        self,
        country: str,
        *,
        search: str | None = None,
        sort: str = "error_sessions",
        direction: Literal["asc", "desc"] = "desc",
    ) -> dict[str, Any]:
        return self._error_table(
            country,
            dataset=DATASET_ERRORS_TOP_ERRORS,
            columns=TOP_ERRORS_COLUMNS,
            required_dataset="derived/errors_top_errors_table",
            search=search,
            sort=sort,
            direction=direction,
            default_sort="error_sessions",
        )

    def app_name_error_table(
        self,
        country: str,
        *,
        search: str | None = None,
        sort: str = "error_session_percent",
        direction: Literal["asc", "desc"] = "desc",
    ) -> dict[str, Any]:
        return self._error_table(
            country,
            dataset=DATASET_ERRORS_APP_NAME,
            columns=ERROR_APP_COLUMNS,
            required_dataset="derived/errors_app_name_table",
            search=search,
            sort=sort,
            direction=direction,
            default_sort="error_session_percent",
        )

    def _error_table(
        self,
        country: str,
        *,
        dataset: str,
        columns: list[TableColumn],
        required_dataset: str,
        search: str | None,
        sort: str,
        direction: Literal["asc", "desc"],
        default_sort: str,
    ) -> dict[str, Any]:
        status = self.status(country)
        if not status["errors_ready"] or not _regression_usable(status["regression_status"]):
            return self._empty_table(country, columns, status, required_dataset)
        rows = self.store.read_country_dataset(country, dataset)
        rows = _filter_rows(rows, search, ("name", "error_name", "app_name"))
        rows = _sort_rows(rows, sort, direction, {column.key for column in columns}, default_sort)
        return {
            "status": "ok" if rows else "empty",
            "country": country,
            "columns": [column.model_dump(mode="json") for column in columns],
            "rows": rows,
            "source": "parquet",
            "reason": None if rows else "No local error rows match the selected filters.",
            "available_datasets": self._available_dataset_names(country),
        }

    def _empty_response(
        self,
        country: str,
        status: dict[str, Any],
        *,
        required_dataset: str,
    ) -> dict[str, Any]:
        return {
            "status": "empty",
            "country": country,
            "source": "parquet",
            "reason": status.get("reason") or "Dashboard local no listo para uso offline.",
            "required_dataset": required_dataset,
            "available_datasets": self._available_dataset_names(country),
            "widgets": [],
            "regression": self._regression_metadata(status),
        }

    def _empty_table(
        self,
        country: str,
        columns: list[TableColumn],
        status: dict[str, Any],
        required_dataset: str,
    ) -> dict[str, Any]:
        return {
            "status": "empty",
            "country": country,
            "columns": [column.model_dump(mode="json") for column in columns],
            "rows": [],
            "source": "parquet",
            "reason": status.get("reason") or "Dashboard local no listo para uso offline.",
            "required_dataset": required_dataset,
            "available_datasets": self._available_dataset_names(country),
        }

    def _tab_ready(self, tab: DashboardTab, contract_roles: set[str]) -> bool:
        return all(role in contract_roles for role in required_roles(tab))

    def _derived_dataset_count(self, country: str) -> int:
        return sum(
            self.store.country_dataset_exists(country, dataset)
            for dataset in (
                DATASET_SUMMARY_WIDGETS,
                DATASET_SUMMARY_TABLE,
                DATASET_ERRORS_WIDGETS,
                DATASET_ERRORS_TOP_ERRORS,
                DATASET_ERRORS_APP_NAME,
            )
        )

    def _raw_calls(self, country: str) -> list[dict[str, Any]]:
        root = self.store.settings.parquet_dir / f"country={country}" / "raw_api_calls"
        files = sorted(root.glob("*.parquet")) if root.exists() else []
        rows: list[dict[str, Any]] = []
        for file in files:
            rows.extend(pl.read_parquet(file).to_dicts())
        return rows

    def _latest_regression(self, country: str) -> dict[str, Any]:
        rows = self.store.read_country_dataset(country, DATASET_REGRESSION_RESULTS)
        if not rows:
            return {}
        return max(rows, key=lambda row: str(row.get("generated_at") or ""))

    def _last_ingestion(self, country: str, key: str) -> str | None:
        rows = [row for row in self.store.list_ingestions() if str(row.get("country")) == country]
        if not rows:
            return None
        latest = max(rows, key=lambda row: str(row.get("started_at") or ""))
        value = latest.get(key)
        return str(value) if value is not None else None

    def _period(self, country: str) -> dict[str, str | None]:
        contracts = self.store.read_country_dataset(country, DATASET_VISUAL_CONTRACTS)
        starts = []
        ends = []
        timezone = None
        for contract in contracts:
            period = contract.get("period")
            if isinstance(period, dict):
                if period.get("start"):
                    starts.append(str(period["start"]))
                if period.get("end"):
                    ends.append(str(period["end"]))
                timezone = timezone or period.get("timezone")
        return {
            "start": min(starts) if starts else None,
            "end": max(ends) if ends else None,
            "timezone": str(timezone) if timezone else None,
        }

    def _available_dataset_names(self, country: str) -> list[str]:
        root = self.store.settings.parquet_dir / f"country={country}"
        if not root.exists():
            return []
        return sorted(
            {
                str(file.parent.relative_to(self.store.settings.parquet_dir))
                for file in root.rglob("*.parquet")
            }
        )

    def _regression_metadata(self, status: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": status.get("regression_status"),
            "verdict": status.get("regression_verdict"),
            "report": status.get("regression_report"),
        }


def _widget_from_row(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("chart_type") == "donut":
        return {
            "id": row.get("id"),
            "role": row.get("card_role"),
            "title": row.get("title") or row.get("card_title"),
            "chart_type": "donut",
            "total": row.get("total"),
            "series": _list(row.get("series")),
            "comparison": row.get("comparison"),
        }
    return {
        "id": row.get("id"),
        "role": row.get("card_role"),
        "title": row.get("title") or row.get("card_title"),
        "value": row.get("value"),
        "unit": row.get("unit") or "count",
        "breakdown": _list(row.get("breakdown")),
        "timeseries": _list(row.get("timeseries")),
        "comparison": row.get("comparison"),
        "missing_source_field": None,
    }


def _regression_usable(status: object) -> bool:
    return status in {"passed", "passed_with_tolerance"}


def _filter_rows(
    rows: list[dict[str, Any]],
    search: str | None,
    fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    if not search:
        return rows
    needle = search.casefold()
    return [
        row
        for row in rows
        if any(needle in str(row.get(field) or "").casefold() for field in fields)
    ]


def _sort_rows(
    rows: list[dict[str, Any]],
    sort: str,
    direction: Literal["asc", "desc"],
    sortable: set[str],
    default_sort: str,
) -> list[dict[str, Any]]:
    sort_key = sort if sort in sortable else default_sort
    return sorted(
        rows,
        key=lambda row: _sort_value(row.get(sort_key)),
        reverse=direction == "desc",
    )


def _sort_value(value: Any) -> tuple[int, Any]:
    if value is None:
        return (0, 0)
    if isinstance(value, (int, float)):
        return (1, value)
    return (1, str(value).casefold())


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def local_dashboard_root(store: ParquetStore, country: str) -> Path:
    return store.settings.parquet_dir / f"country={country}"
