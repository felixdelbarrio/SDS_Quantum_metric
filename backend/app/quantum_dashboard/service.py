from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import polars as pl

from backend.app.analytics.models import TableColumn
from backend.app.observability.sanitizer import sanitize_error
from backend.app.quantum.config_store import QuantumConfigStore
from backend.app.quantum.schemas import COUNTRY_LABELS, COUNTRY_ORDER, Country
from backend.app.quantum_dashboard.builder import (
    DATASET_CHART_PAYLOADS,
    DATASET_ERRORS_APP_NAME,
    DATASET_ERRORS_TOP_ERRORS,
    DATASET_ERRORS_WIDGETS,
    DATASET_REGRESSION_RESULTS,
    DATASET_SUMMARY_TABLE,
    DATASET_SUMMARY_WIDGETS,
    DATASET_VISUAL_CONTRACTS,
    build_derived_datasets,
    range_dataset_path,
)
from backend.app.quantum_dashboard.catalog import MANDATORY_CARDS, required_roles
from backend.app.quantum_dashboard.models import DashboardTab
from backend.app.quantum_dashboard.periods import format_period_label, parse_datetime
from backend.app.quantum_dashboard.regression import REGRESSION_REPORT_PATH, run_regression
from backend.app.storage.parquet_store import ParquetStore

SUMMARY_COLUMNS = [
    TableColumn(key="name", label="name", sortable=True),
    TableColumn(key="app_name", label="App Name", sortable=True),
    TableColumn(key="operating_system", label="Sistema operativo", sortable=True),
    TableColumn(key="page_views", label="Page Views", sortable=True),
    TableColumn(key="page_views_delta_percent", label="Delta Page Views", sortable=True),
    TableColumn(key="sessions", label="Sessions", sortable=True),
    TableColumn(key="sessions_delta_percent", label="Delta Sessions", sortable=True),
    TableColumn(key="conversions", label="General - Conversiones", sortable=True),
    TableColumn(key="conversions_delta_percent", label="Delta Conversiones", sortable=True),
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
    def __init__(self, store: ParquetStore, config_store: QuantumConfigStore | None = None) -> None:
        self.store = store
        self.config_store = config_store

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
                    "dashboard_id": status.get("dashboard_id"),
                    "dashboard_name": status.get("dashboard_name"),
                }
            )
        configured = str(self.store.settings.qm_country or Country.MX.value)
        return {"countries": countries, "default_country": first_ready or configured}

    def status(
        self,
        country: str,
        *,
        range_key: str = "today",
        dashboard_id: str | None = None,
    ) -> dict[str, Any]:
        dashboard = self._resolve_dashboard(country, dashboard_id)
        resolved_dashboard_id = dashboard.get("dashboard_id")
        enabled_roles = self._enabled_roles(country, resolved_dashboard_id)
        repair_error = self._ensure_range_contract(
            country, range_key, enabled_roles, resolved_dashboard_id
        )
        all_raw_calls = self._raw_calls(country, resolved_dashboard_id)
        raw_calls = self._raw_calls_for_range(country, range_key, resolved_dashboard_id)
        contracts = self._read_dataset(
            country, DATASET_VISUAL_CONTRACTS, range_key, resolved_dashboard_id
        )
        contract_roles = {str(row.get("visual_role")) for row in contracts}
        contract_roles = {role for role in contract_roles if role in enabled_roles}
        regression = self._latest_regression(country, range_key, resolved_dashboard_id)
        summary_ready = self._tab_ready("summary", contract_roles, enabled_roles) and (
            self._dataset_ready_for_dashboard(
                country, DATASET_SUMMARY_WIDGETS, range_key, resolved_dashboard_id
            )
            and self._dataset_ready_for_dashboard(
                country, DATASET_SUMMARY_TABLE, range_key, resolved_dashboard_id
            )
        )
        errors_ready = self._tab_ready("errors", contract_roles, enabled_roles) and (
            self._dataset_ready_for_dashboard(
                country, DATASET_ERRORS_WIDGETS, range_key, resolved_dashboard_id
            )
            and self._dataset_ready_for_dashboard(
                country, DATASET_ERRORS_TOP_ERRORS, range_key, resolved_dashboard_id
            )
            and self._dataset_ready_for_dashboard(
                country, DATASET_ERRORS_APP_NAME, range_key, resolved_dashboard_id
            )
        )
        missing_roles = [
            role
            for role in required_roles()
            if role in enabled_roles and role not in contract_roles
        ]
        reason = None
        if raw_calls and missing_roles:
            reason = (
                "Quantum responses were captured but mandatory card roles were not mapped: "
                + ", ".join(missing_roles)
            )
        elif raw_calls and not (summary_ready and errors_ready):
            reason = (
                "Datos raw disponibles, pero no existe dataset analitico derivado completo. "
                "La reconstruccion automatica no pudo dejarlo listo."
            )
        elif all_raw_calls and not contracts:
            reason = "No hay ingesta local para el rango seleccionado."
        if repair_error:
            reason = f"No se pudo completar la reparacion automatica: {repair_error}"
        mandatory_roles = [role for role in required_roles() if role in enabled_roles]
        return {
            "country": country,
            "dashboard_id": resolved_dashboard_id,
            "dashboard_name": dashboard.get("dashboard_name"),
            "range_key": range_key,
            "has_data": bool(all_raw_calls or contracts),
            "last_ingestion_id": self._last_ingestion(
                country, "ingestion_id", resolved_dashboard_id
            ),
            "last_ingestion_at": self._last_ingestion(country, "started_at", resolved_dashboard_id),
            "regression_status": regression.get("status") or "failed_missing_card",
            "regression_verdict": regression.get("verdict"),
            "calls": len(raw_calls),
            "rows": sum(int(row.get("row_count") or 0) for row in raw_calls),
            "cards": len(contract_roles),
            "captured_cards": len(contract_roles),
            "mandatory_cards": len(mandatory_roles),
            "mandatory_cards_captured": len(mandatory_roles) - len(missing_roles),
            "summary_ready": summary_ready,
            "errors_ready": errors_ready,
            "derived_datasets": self._derived_dataset_count(country, range_key),
            "reason": reason,
            "missing_roles": missing_roles,
            "regression_report": REGRESSION_REPORT_PATH if regression else None,
        }

    def summary(
        self,
        country: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        range_key: str = "today",
        dashboard_id: str | None = None,
    ) -> dict[str, Any]:
        status = self.status(country, range_key=range_key, dashboard_id=dashboard_id)
        if not status["summary_ready"] or not _regression_usable(status["regression_status"]):
            return self._empty_response(country, status, required_dataset="derived/summary")
        period = self._period(country, range_key, status.get("dashboard_id"))
        if not _period_matches(period, start_date, end_date):
            return self._empty_response(
                country,
                {**status, "reason": "No hay ingesta local para el rango de fechas seleccionado."},
                required_dataset="derived/summary",
            )
        widgets = [
            _widget_from_row(row)
            for row in self._read_dataset(
                country, DATASET_SUMMARY_WIDGETS, range_key, status.get("dashboard_id")
            )
            if str(row.get("card_role")) in self._enabled_roles(country, status.get("dashboard_id"))
        ]
        order = {card.local_id: index for index, card in enumerate(MANDATORY_CARDS)}
        widgets.sort(key=lambda item: order.get(str(item["id"]), 99))
        return {
            "status": "ok",
            "country": country,
            "range_key": range_key,
            "source": "parquet",
            "last_ingestion_at": status["last_ingestion_at"],
            "dashboard_title": status.get("dashboard_name") or f"Dashboard General {country}",
            "dashboard_id": status.get("dashboard_id"),
            "dashboard_name": status.get("dashboard_name"),
            "description": "Este dashboard es un resumen de sesiones y errores.",
            "widgets": widgets,
            "period": period,
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
        start_date: str | None = None,
        end_date: str | None = None,
        range_key: str = "today",
        dashboard_id: str | None = None,
    ) -> dict[str, Any]:
        status = self.status(country, range_key=range_key, dashboard_id=dashboard_id)
        if not status["summary_ready"] or not _regression_usable(status["regression_status"]):
            return self._empty_table(
                country, SUMMARY_COLUMNS, status, "derived/summary_detail_table"
            )
        period = self._period(country, range_key, status.get("dashboard_id"))
        if not _period_matches(period, start_date, end_date):
            return self._empty_table(
                country,
                SUMMARY_COLUMNS,
                {**status, "reason": "No hay ingesta local para el rango de fechas seleccionado."},
                "derived/summary_detail_table",
            )
        rows = self._read_dataset(
            country, DATASET_SUMMARY_TABLE, range_key, status.get("dashboard_id")
        )
        rows = [
            row
            for row in rows
            if str(row.get("card_role")) in self._enabled_roles(country, status.get("dashboard_id"))
        ]
        rows = _normalize_table_hierarchy(rows)
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
            "period": period,
        }

    def errors(
        self,
        country: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        range_key: str = "today",
        dashboard_id: str | None = None,
    ) -> dict[str, Any]:
        status = self.status(country, range_key=range_key, dashboard_id=dashboard_id)
        if not status["errors_ready"] or not _regression_usable(status["regression_status"]):
            return self._empty_response(country, status, required_dataset="derived/errors")
        period = self._period(country, range_key, status.get("dashboard_id"))
        if not _period_matches(period, start_date, end_date):
            return self._empty_response(
                country,
                {**status, "reason": "No hay ingesta local para el rango de fechas seleccionado."},
                required_dataset="derived/errors",
            )
        widgets = [
            _widget_from_row(row)
            for row in self._read_dataset(
                country, DATASET_ERRORS_WIDGETS, range_key, status.get("dashboard_id")
            )
            if str(row.get("card_role")) in self._enabled_roles(country, status.get("dashboard_id"))
        ]
        return {
            "status": "ok",
            "country": country,
            "range_key": range_key,
            "source": "parquet",
            "last_ingestion_at": status["last_ingestion_at"],
            "dashboard_id": status.get("dashboard_id"),
            "dashboard_name": status.get("dashboard_name"),
            "widgets": widgets,
            "period": period,
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
        start_date: str | None = None,
        end_date: str | None = None,
        range_key: str = "today",
        dashboard_id: str | None = None,
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
            start_date=start_date,
            end_date=end_date,
            range_key=range_key,
            dashboard_id=dashboard_id,
        )

    def app_name_error_table(
        self,
        country: str,
        *,
        search: str | None = None,
        sort: str = "row_index",
        direction: Literal["asc", "desc"] = "asc",
        start_date: str | None = None,
        end_date: str | None = None,
        range_key: str = "today",
        dashboard_id: str | None = None,
    ) -> dict[str, Any]:
        return self._error_table(
            country,
            dataset=DATASET_ERRORS_APP_NAME,
            columns=ERROR_APP_COLUMNS,
            required_dataset="derived/errors_app_name_table",
            search=search,
            sort=sort,
            direction=direction,
            default_sort="row_index",
            start_date=start_date,
            end_date=end_date,
            range_key=range_key,
            dashboard_id=dashboard_id,
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
        start_date: str | None,
        end_date: str | None,
        range_key: str,
        dashboard_id: str | None = None,
    ) -> dict[str, Any]:
        status = self.status(country, range_key=range_key, dashboard_id=dashboard_id)
        if not status["errors_ready"] or not _regression_usable(status["regression_status"]):
            return self._empty_table(country, columns, status, required_dataset)
        period = self._period(country, range_key, status.get("dashboard_id"))
        if not _period_matches(period, start_date, end_date):
            return self._empty_table(
                country,
                columns,
                {**status, "reason": "No hay ingesta local para el rango de fechas seleccionado."},
                required_dataset,
            )
        rows = self._read_dataset(country, dataset, range_key, status.get("dashboard_id"))
        rows = [
            row
            for row in rows
            if str(row.get("card_role")) in self._enabled_roles(country, status.get("dashboard_id"))
        ]
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
            "period": period,
        }

    def card_detail(
        self,
        country: str,
        card_role: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        range_key: str = "today",
        dashboard_id: str | None = None,
    ) -> dict[str, Any]:
        dashboard = self._resolve_dashboard(country, dashboard_id)
        resolved_dashboard_id = dashboard.get("dashboard_id")
        widget = self._card_widget(country, card_role, range_key, resolved_dashboard_id)
        rows = self._card_rows(country, card_role, range_key, resolved_dashboard_id)
        period = self._period(country, range_key, resolved_dashboard_id)
        if not _period_matches(period, start_date, end_date):
            return {
                "status": "empty",
                "country": country,
                "dashboard_id": resolved_dashboard_id,
                "dashboard_name": dashboard.get("dashboard_name"),
                "card_role": card_role,
                "reason": "No hay ingesta local para el rango de fechas seleccionado.",
                "rows": [],
                "points": [],
            }
        points = _chart_points(widget.get("chart_payload") if widget else None)
        return {
            "status": "ok" if widget or rows else "empty",
            "country": country,
            "dashboard_id": resolved_dashboard_id,
            "dashboard_name": dashboard.get("dashboard_name"),
            "card_role": card_role,
            "title": (widget or {}).get("title")
            or (rows[0].get("card_title") if rows else card_role),
            "value": (widget or {}).get("value") or (widget or {}).get("total"),
            "unit": (widget or {}).get("unit"),
            "period": period,
            "widget": widget,
            "rows": rows,
            "points": points,
            "video_notice": "La reproduccion de sesiones solo esta disponible en Quantum Web.",
            "source": "parquet",
        }

    def card_breakdown(
        self,
        country: str,
        card_role: str,
        *,
        range_key: str = "today",
        dashboard_id: str | None = None,
    ) -> dict[str, Any]:
        dashboard = self._resolve_dashboard(country, dashboard_id)
        resolved_dashboard_id = dashboard.get("dashboard_id")
        widget = self._card_widget(country, card_role, range_key, resolved_dashboard_id) or {}
        return {
            "status": "ok" if widget else "empty",
            "country": country,
            "dashboard_id": resolved_dashboard_id,
            "dashboard_name": dashboard.get("dashboard_name"),
            "card_role": card_role,
            "breakdown": widget.get("breakdown") or widget.get("series") or [],
            "source": "parquet",
        }

    def card_points(
        self,
        country: str,
        card_role: str,
        *,
        range_key: str = "today",
        dashboard_id: str | None = None,
    ) -> dict[str, Any]:
        dashboard = self._resolve_dashboard(country, dashboard_id)
        resolved_dashboard_id = dashboard.get("dashboard_id")
        widget = self._card_widget(country, card_role, range_key, resolved_dashboard_id) or {}
        return {
            "status": "ok" if widget else "empty",
            "country": country,
            "dashboard_id": resolved_dashboard_id,
            "dashboard_name": dashboard.get("dashboard_name"),
            "card_role": card_role,
            "points": _chart_points(widget.get("chart_payload")),
            "source": "parquet",
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
            "range_key": status.get("range_key"),
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
            "range_key": status.get("range_key"),
            "columns": [column.model_dump(mode="json") for column in columns],
            "rows": [],
            "source": "parquet",
            "reason": status.get("reason") or "Dashboard local no listo para uso offline.",
            "required_dataset": required_dataset,
            "available_datasets": self._available_dataset_names(country),
        }

    def _ensure_range_contract(
        self,
        country: str,
        range_key: str,
        enabled_roles: set[str],
        dashboard_id: str | None = None,
    ) -> str | None:
        raw_calls = self._raw_calls_for_range(country, range_key, dashboard_id)
        if not raw_calls:
            return None
        derived_ready = all(
            self._dataset_ready_for_dashboard(country, dataset, range_key, dashboard_id)
            for dataset in (
                DATASET_SUMMARY_WIDGETS,
                DATASET_SUMMARY_TABLE,
                DATASET_ERRORS_WIDGETS,
                DATASET_ERRORS_TOP_ERRORS,
                DATASET_ERRORS_APP_NAME,
                DATASET_CHART_PAYLOADS,
            )
        )
        regression = self._latest_regression(country, range_key, dashboard_id)
        regression_ready = _regression_usable(
            regression.get("status")
        ) and self._dataset_ready_for_dashboard(
            country, DATASET_REGRESSION_RESULTS, range_key, dashboard_id
        )
        if derived_ready and regression_ready:
            return None
        try:
            if not derived_ready:
                build_derived_datasets(
                    self.store,
                    country,
                    raw_calls=raw_calls,
                    enabled_roles=enabled_roles,
                    dashboard_id=dashboard_id,
                    dashboard_name=self._resolve_dashboard(country, dashboard_id).get(
                        "dashboard_name"
                    ),
                    range_key=range_key,
                )
            if not regression_ready:
                run_regression(
                    self.store,
                    country,
                    enabled_roles=enabled_roles,
                    dashboard_id=dashboard_id,
                    range_key=range_key,
                )
        except Exception as exc:
            return sanitize_error(exc)
        return None

    def _tab_ready(
        self,
        tab: DashboardTab,
        contract_roles: set[str],
        enabled_roles: set[str],
    ) -> bool:
        return all(role in contract_roles for role in required_roles(tab) if role in enabled_roles)

    def _derived_dataset_count(self, country: str, range_key: str) -> int:
        return sum(
            self._dataset_exists(country, dataset, range_key)
            for dataset in (
                DATASET_SUMMARY_WIDGETS,
                DATASET_SUMMARY_TABLE,
                DATASET_ERRORS_WIDGETS,
                DATASET_ERRORS_TOP_ERRORS,
                DATASET_ERRORS_APP_NAME,
                DATASET_CHART_PAYLOADS,
            )
        )

    def _raw_calls(self, country: str, dashboard_id: str | None = None) -> list[dict[str, Any]]:
        root = self.store.settings.parquet_dir / f"country={country}" / "raw_api_calls"
        files = sorted(root.glob("*.parquet")) if root.exists() else []
        rows: list[dict[str, Any]] = []
        for file in files:
            rows.extend(pl.read_parquet(file).to_dicts())
        return _filter_dashboard_rows(rows, dashboard_id)

    def _raw_calls_for_range(
        self, country: str, range_key: str, dashboard_id: str | None = None
    ) -> list[dict[str, Any]]:
        key = _safe_range_key(range_key)
        return [
            row
            for row in self._raw_calls(country, dashboard_id)
            if _safe_range_key(_text(row.get("range_key")) or "today") == key
        ]

    def _latest_regression(
        self,
        country: str,
        range_key: str = "today",
        dashboard_id: str | None = None,
    ) -> dict[str, Any]:
        rows = self._read_dataset(country, DATASET_REGRESSION_RESULTS, range_key, dashboard_id)
        if not rows:
            return {}
        return max(rows, key=lambda row: str(row.get("generated_at") or ""))

    def _last_ingestion(
        self,
        country: str,
        key: str,
        dashboard_id: str | None = None,
    ) -> str | None:
        rows = [row for row in self.store.list_ingestions() if str(row.get("country")) == country]
        if dashboard_id:
            scoped = [
                row
                for row in rows
                if isinstance(row.get("details"), dict)
                and ((row.get("details") or {}).get("dashboard") or {}).get("dashboard_id")
                == dashboard_id
            ]
            if scoped:
                rows = scoped
        if not rows:
            return None
        latest = max(rows, key=lambda row: str(row.get("started_at") or ""))
        value = latest.get(key)
        return str(value) if value is not None else None

    def _period(
        self,
        country: str,
        range_key: str,
        dashboard_id: str | None = None,
    ) -> dict[str, str | None]:
        for dataset in (
            DATASET_VISUAL_CONTRACTS,
            DATASET_SUMMARY_WIDGETS,
            DATASET_ERRORS_WIDGETS,
            DATASET_CHART_PAYLOADS,
        ):
            period = _first_period(
                self._read_dataset(country, dataset, range_key, dashboard_id), range_key
            )
            if period["start"] or period["end"]:
                return period
        return _period_response(None, None, None)

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

    def _card_widget(
        self,
        country: str,
        card_role: str,
        range_key: str,
        dashboard_id: str | None = None,
    ) -> dict[str, Any] | None:
        rows = [
            *self._read_dataset(country, DATASET_SUMMARY_WIDGETS, range_key, dashboard_id),
            *self._read_dataset(country, DATASET_ERRORS_WIDGETS, range_key, dashboard_id),
        ]
        for row in rows:
            if row.get("card_role") == card_role and card_role in self._enabled_roles(
                country, dashboard_id
            ):
                return _widget_from_row(row)
        return None

    def _card_rows(
        self,
        country: str,
        card_role: str,
        range_key: str,
        dashboard_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if card_role == "summary.detail_by_app_name_os":
            dataset = DATASET_SUMMARY_TABLE
        elif card_role == "errors.top_errors_by_error_name":
            dataset = DATASET_ERRORS_TOP_ERRORS
        elif card_role == "errors.error_session_percentage_by_app_name":
            dataset = DATASET_ERRORS_APP_NAME
        else:
            return []
        return [
            row
            for row in self._read_dataset(country, dataset, range_key, dashboard_id)
            if row.get("card_role") == card_role
            and card_role in self._enabled_roles(country, dashboard_id)
        ]

    def _enabled_roles(self, country: str, dashboard_id: str | None = None) -> set[str]:
        if self.config_store is None:
            return set(required_roles())
        try:
            config = self.config_store.read()
            country_config = config.country_config(country)
        except Exception:
            return set(required_roles())
        if country_config is None:
            return set(required_roles())
        dashboard = None
        if dashboard_id:
            dashboard = next(
                (item for item in country_config.dashboards if item.dashboard_id == dashboard_id),
                None,
            )
        if dashboard is None:
            dashboard = country_config.default_dashboard()
        if dashboard is None:
            return set(required_roles())
        return set(dashboard.enabled_widget_roles())

    def _read_dataset(
        self,
        country: str,
        dataset_path: str,
        range_key: str,
        dashboard_id: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self.store.read_country_dataset(country, range_dataset_path(dataset_path, range_key))
        if not rows and range_key == "today":
            rows = self.store.read_country_dataset(country, dataset_path)
        return _filter_dashboard_rows(rows, dashboard_id)

    def _dataset_exists(self, country: str, dataset_path: str, range_key: str) -> bool:
        if self.store.country_dataset_exists(country, range_dataset_path(dataset_path, range_key)):
            return True
        return range_key == "today" and self.store.country_dataset_exists(country, dataset_path)

    def _dataset_ready_for_dashboard(
        self,
        country: str,
        dataset_path: str,
        range_key: str,
        dashboard_id: str | None = None,
    ) -> bool:
        if not self._dataset_exists(country, dataset_path, range_key):
            return False
        if not dashboard_id:
            return True
        rows = self.store.read_country_dataset(country, range_dataset_path(dataset_path, range_key))
        if not rows and range_key == "today":
            rows = self.store.read_country_dataset(country, dataset_path)
        return any(_text(row.get("dashboard_id")) == dashboard_id for row in rows)

    def _resolve_dashboard(
        self,
        country: str,
        dashboard_id: str | None = None,
    ) -> dict[str, str | None]:
        if dashboard_id:
            return {"dashboard_id": dashboard_id, "dashboard_name": None}
        if self.config_store is None:
            return {"dashboard_id": None, "dashboard_name": None}
        try:
            country_config = self.config_store.read().country_config(country)
        except Exception:
            return {"dashboard_id": None, "dashboard_name": None}
        dashboard = country_config.default_dashboard() if country_config is not None else None
        if dashboard is None:
            return {"dashboard_id": None, "dashboard_name": None}
        return {
            "dashboard_id": dashboard.dashboard_id or None,
            "dashboard_name": dashboard.name or None,
        }


def _filter_dashboard_rows(
    rows: list[dict[str, Any]],
    dashboard_id: str | None,
) -> list[dict[str, Any]]:
    if not dashboard_id:
        return rows
    return [row for row in rows if _text(row.get("dashboard_id")) == dashboard_id]


def _widget_from_row(row: dict[str, Any]) -> dict[str, Any]:
    period = {
        "start": _text(row.get("period_start")),
        "end": _text(row.get("period_end")),
        "timezone": _text(row.get("period_timezone")) or "CST",
    }
    period["label"] = _period_label(
        period["start"],
        period["end"],
        period["timezone"],
        _period_preset(_text(row.get("range_key"))),
    )
    if row.get("chart_type") == "donut":
        series = _list(row.get("series"))
        return {
            "id": row.get("id"),
            "role": row.get("card_role"),
            "dashboard_id": row.get("dashboard_id"),
            "dashboard_name": row.get("dashboard_name"),
            "widget_id": row.get("widget_id"),
            "range_key": row.get("range_key"),
            "title": row.get("title") or row.get("card_title"),
            "chart_type": "donut",
            "value": row.get("total"),
            "unit": "count",
            "breakdown": series,
            "total": row.get("total"),
            "series": series,
            "chart_payload": _with_period_label(row.get("chart_payload"), period),
            "comparison": row.get("comparison"),
            "delta_percent": row.get("delta_percent"),
            "semantic_state": row.get("semantic_state"),
            "semantic_intent": row.get("semantic_intent"),
            "period": period,
        }
    return {
        "id": row.get("id"),
        "role": row.get("card_role"),
        "dashboard_id": row.get("dashboard_id"),
        "dashboard_name": row.get("dashboard_name"),
        "widget_id": row.get("widget_id"),
        "range_key": row.get("range_key"),
        "title": row.get("title") or row.get("card_title"),
        "value": row.get("value"),
        "unit": row.get("unit") or "count",
        "breakdown": _list(row.get("breakdown")),
        "timeseries": _list(row.get("timeseries")),
        "chart_payload": _with_period_label(row.get("chart_payload"), period),
        "comparison": row.get("comparison"),
        "delta_percent": row.get("delta_percent"),
        "semantic_state": row.get("semantic_state"),
        "semantic_intent": row.get("semantic_intent"),
        "missing_source_field": None,
        "period": period,
    }


def _with_period_label(value: Any, period: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    payload = dict(value)
    current_label = _text(payload.get("period_label"))
    payload["period_label"] = (
        period.get("label") if _is_epoch_period_label(current_label) else current_label
    ) or period.get("label")
    payload["timezone"] = payload.get("timezone") or period.get("timezone")
    return payload


def _is_epoch_period_label(value: str | None) -> bool:
    if not value:
        return False
    parts = value.replace("CST", "").replace("UTC", "").split("-")
    if len(parts) < 2:
        return False
    return all(part.strip().isdigit() and len(part.strip()) in {10, 13} for part in parts[:2])


def _chart_points(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    points: list[dict[str, Any]] = []
    for series in _list(value.get("series")):
        if not isinstance(series, dict):
            continue
        for point in _list(series.get("points")):
            if isinstance(point, dict):
                points.append(
                    {
                        "series": series.get("label"),
                        "ts": point.get("ts"),
                        "label": point.get("label"),
                        "value": point.get("value"),
                    }
                )
    return points


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


def _normalize_table_hierarchy(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [{**row} for row in rows]
    children_by_parent: dict[str, int] = {}
    for row in normalized:
        parent = row.get("parent_row_id")
        if parent not in (None, ""):
            children_by_parent[str(parent)] = children_by_parent.get(str(parent), 0) + 1
    for row in normalized:
        row_id = row.get("row_id")
        children_count = children_by_parent.get(str(row_id), 0) if row_id not in (None, "") else 0
        row["children_count"] = children_count
        row["is_expandable"] = bool(row.get("is_expandable")) and children_count > 0
        if not row["is_expandable"]:
            row["is_expanded_default"] = False
    return normalized


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


def _number(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0


def _first_period(rows: list[dict[str, Any]], preset: str | None = None) -> dict[str, str | None]:
    for row in rows:
        row_preset = _period_preset(_text(row.get("range_key")) or preset)
        period = row.get("period")
        if isinstance(period, dict):
            start = _text(period.get("start"))
            end = _text(period.get("end"))
            timezone = _text(period.get("timezone"))
            if start or end:
                return _period_response(start, end, timezone, row_preset)
        start = _text(row.get("range_start") or row.get("period_start") or row.get("start"))
        end = _text(row.get("range_end") or row.get("period_end") or row.get("end"))
        timezone = _text(
            row.get("range_timezone") or row.get("period_timezone") or row.get("timezone")
        )
        if start or end:
            return _period_response(start, end, timezone, row_preset)
    return _period_response(None, None, None)


def _period_response(
    start: str | None,
    end: str | None,
    timezone: str | None,
    preset: str | None = None,
) -> dict[str, str | None]:
    zone = timezone or "CST"
    return {
        "start": start,
        "end": end,
        "timezone": timezone,
        "label": _period_label(start, end, zone, preset),
    }


def _period_matches(
    period: dict[str, Any],
    start_date: str | None,
    end_date: str | None,
) -> bool:
    if not start_date and not end_date:
        return True
    period_start = _period_date(period.get("start"), period.get("timezone"))
    period_end = _period_date(period.get("end"), period.get("timezone")) or period_start
    if period_start is None:
        return False
    requested_start = _parse_date(start_date) or period_start
    requested_end = _parse_date(end_date) or requested_start
    if requested_start is None or requested_end is None or period_end is None:
        return False
    return period_start <= requested_end and period_end >= requested_start


def _period_date(value: Any, timezone: Any) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        parsed = _parse_date(text[:10])
        return parsed
    zone = _zone(str(timezone or "CST"))
    return datetime.fromtimestamp(number, UTC).astimezone(zone).date()


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _period_label(
    start: Any,
    end: Any,
    timezone: str | None,
    preset: str | None = None,
) -> str | None:
    zone_label = timezone or "CST"
    start_dt = parse_datetime(start, zone_label)
    end_dt = parse_datetime(end, zone_label)
    if start_dt is None and end_dt is None:
        return None
    start_dt = start_dt or end_dt
    end_dt = end_dt or start_dt
    if start_dt is None or end_dt is None:
        return None
    return format_period_label(start_dt, end_dt, zone_label, preset)


def _period_preset(range_key: str | None) -> str | None:
    preset = _safe_range_key(range_key)
    return preset if preset in {"today", "yesterday", "last_7_days", "custom"} else None


def _zone(timezone: str) -> ZoneInfo:
    if timezone == "CST":
        return ZoneInfo("America/Mexico_City")
    if timezone == "UTC":
        return ZoneInfo("UTC")
    return ZoneInfo("America/Mexico_City")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_range_key(range_key: str | None) -> str:
    raw = (range_key or "").strip().lower()
    if raw in {"today", "yesterday", "last_7_days", "custom"}:
        return raw
    return "".join(
        character if character.isalnum() or character == "_" else "_" for character in raw
    )


def local_dashboard_root(store: ParquetStore, country: str) -> Path:
    return store.settings.parquet_dir / f"country={country}"
