from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import polars as pl

from backend.app.analytics.models import TableColumn
from backend.app.analytics.normalizer import humanize_key
from backend.app.analytics.segments import parse_segment
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
)
from backend.app.quantum_dashboard.catalog import MANDATORY_CARDS, required_roles
from backend.app.quantum_dashboard.models import DashboardTab
from backend.app.quantum_dashboard.periods import format_period_label, parse_datetime
from backend.app.quantum_dashboard.regression import REGRESSION_REPORT_PATH
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
                }
            )
        configured = str(self.store.settings.qm_country or Country.MX.value)
        return {"countries": countries, "default_country": first_ready or configured}

    def status(self, country: str) -> dict[str, Any]:
        raw_calls = self._raw_calls(country)
        contracts = self.store.read_country_dataset(country, DATASET_VISUAL_CONTRACTS)
        contract_roles = {str(row.get("visual_role")) for row in contracts}
        enabled_roles = self._enabled_roles(country)
        contract_roles = {role for role in contract_roles if role in enabled_roles}
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
            "mandatory_cards": len([role for role in required_roles() if role in enabled_roles]),
            "mandatory_cards_captured": len(required_roles()) - len(missing_roles),
            "summary_ready": summary_ready,
            "errors_ready": errors_ready,
            "derived_datasets": self._derived_dataset_count(country),
            "reason": reason,
            "missing_roles": missing_roles,
            "regression_report": REGRESSION_REPORT_PATH if regression else None,
        }

    def summary(
        self,
        country: str,
        *,
        dimension: str | None = None,
        segment: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        status = self.status(country)
        if not status["summary_ready"] or not _regression_usable(status["regression_status"]):
            return self._empty_response(country, status, required_dataset="derived/summary")
        period = self._period(country)
        if not _period_matches(period, start_date, end_date):
            return self._empty_response(
                country,
                {**status, "reason": "No hay ingesta local para el rango de fechas seleccionado."},
                required_dataset="derived/summary",
            )
        widgets = [
            _widget_from_row(row)
            for row in self.store.read_country_dataset(country, DATASET_SUMMARY_WIDGETS)
            if str(row.get("card_role")) in self._enabled_roles(country)
        ]
        if segment:
            widgets = _summary_widgets_for_segment(
                widgets,
                self.store.read_country_dataset(country, DATASET_SUMMARY_TABLE),
                segment,
            )
        order = {card.local_id: index for index, card in enumerate(MANDATORY_CARDS)}
        widgets.sort(key=lambda item: order.get(str(item["id"]), 99))
        return {
            "status": "ok",
            "country": country,
            "source": "parquet",
            "last_ingestion_at": status["last_ingestion_at"],
            "dashboard_title": f"Dashboard General {country}",
            "description": "Este dashboard es un resumen de sesiones y errores.",
            "applied_dimension": _selection(dimension),
            "applied_segment": _segment_selection(segment),
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
        dimension: str | None = None,
        segment: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        status = self.status(country)
        if not status["summary_ready"] or not _regression_usable(status["regression_status"]):
            return self._empty_table(
                country, SUMMARY_COLUMNS, status, "derived/summary_detail_table"
            )
        period = self._period(country)
        if not _period_matches(period, start_date, end_date):
            return self._empty_table(
                country,
                SUMMARY_COLUMNS,
                {**status, "reason": "No hay ingesta local para el rango de fechas seleccionado."},
                "derived/summary_detail_table",
            )
        rows = self.store.read_country_dataset(country, DATASET_SUMMARY_TABLE)
        rows = [row for row in rows if str(row.get("card_role")) in self._enabled_roles(country)]
        rows = _apply_segment(rows, segment)
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
            "applied_dimension": _selection(dimension),
            "applied_segment": _segment_selection(segment),
            "reason": None if rows else "No local summary rows match the selected filters.",
            "available_datasets": self._available_dataset_names(country),
            "period": period,
        }

    def errors(
        self,
        country: str,
        *,
        dimension: str | None = None,
        segment: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        status = self.status(country)
        if not status["errors_ready"] or not _regression_usable(status["regression_status"]):
            return self._empty_response(country, status, required_dataset="derived/errors")
        period = self._period(country)
        if not _period_matches(period, start_date, end_date):
            return self._empty_response(
                country,
                {**status, "reason": "No hay ingesta local para el rango de fechas seleccionado."},
                required_dataset="derived/errors",
            )
        widgets = [
            _widget_from_row(row)
            for row in self.store.read_country_dataset(country, DATASET_ERRORS_WIDGETS)
            if str(row.get("card_role")) in self._enabled_roles(country)
        ]
        if segment:
            widgets = _error_widgets_for_segment(
                widgets,
                self.store.read_country_dataset(country, DATASET_ERRORS_APP_NAME),
                segment,
            )
        return {
            "status": "ok",
            "country": country,
            "source": "parquet",
            "last_ingestion_at": status["last_ingestion_at"],
            "applied_dimension": _selection(dimension),
            "applied_segment": _segment_selection(segment),
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
        dimension: str | None = None,
        segment: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
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
            dimension=dimension,
            segment=segment,
            start_date=start_date,
            end_date=end_date,
        )

    def app_name_error_table(
        self,
        country: str,
        *,
        search: str | None = None,
        sort: str = "error_session_percent",
        direction: Literal["asc", "desc"] = "desc",
        dimension: str | None = None,
        segment: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
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
            dimension=dimension,
            segment=segment,
            start_date=start_date,
            end_date=end_date,
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
        dimension: str | None,
        segment: str | None,
        start_date: str | None,
        end_date: str | None,
    ) -> dict[str, Any]:
        status = self.status(country)
        if not status["errors_ready"] or not _regression_usable(status["regression_status"]):
            return self._empty_table(country, columns, status, required_dataset)
        period = self._period(country)
        if not _period_matches(period, start_date, end_date):
            return self._empty_table(
                country,
                columns,
                {**status, "reason": "No hay ingesta local para el rango de fechas seleccionado."},
                required_dataset,
            )
        rows = self.store.read_country_dataset(country, dataset)
        rows = [row for row in rows if str(row.get("card_role")) in self._enabled_roles(country)]
        rows = _apply_segment(rows, segment)
        rows = _filter_rows(rows, search, ("name", "error_name", "app_name"))
        rows = _sort_rows(rows, sort, direction, {column.key for column in columns}, default_sort)
        return {
            "status": "ok" if rows else "empty",
            "country": country,
            "columns": [column.model_dump(mode="json") for column in columns],
            "rows": rows,
            "source": "parquet",
            "applied_dimension": _selection(dimension),
            "applied_segment": _segment_selection(segment),
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
    ) -> dict[str, Any]:
        widget = self._card_widget(country, card_role)
        rows = self._card_rows(country, card_role)
        period = self._period(country)
        if not _period_matches(period, start_date, end_date):
            return {
                "status": "empty",
                "country": country,
                "card_role": card_role,
                "reason": "No hay ingesta local para el rango de fechas seleccionado.",
                "rows": [],
                "points": [],
            }
        points = _chart_points(widget.get("chart_payload") if widget else None)
        return {
            "status": "ok" if widget or rows else "empty",
            "country": country,
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

    def card_breakdown(self, country: str, card_role: str) -> dict[str, Any]:
        widget = self._card_widget(country, card_role) or {}
        return {
            "status": "ok" if widget else "empty",
            "country": country,
            "card_role": card_role,
            "breakdown": widget.get("breakdown") or widget.get("series") or [],
            "source": "parquet",
        }

    def card_points(self, country: str, card_role: str) -> dict[str, Any]:
        widget = self._card_widget(country, card_role) or {}
        return {
            "status": "ok" if widget else "empty",
            "country": country,
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
                DATASET_CHART_PAYLOADS,
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
        rows = [
            *self.store.read_country_dataset(country, DATASET_VISUAL_CONTRACTS),
            *self.store.read_country_dataset(country, DATASET_SUMMARY_WIDGETS),
            *self.store.read_country_dataset(country, DATASET_ERRORS_WIDGETS),
            *self.store.read_country_dataset(country, DATASET_CHART_PAYLOADS),
        ]
        starts: list[str] = []
        ends: list[str] = []
        timezone: object | None = None
        for row in rows:
            period = row.get("period")
            if isinstance(period, dict):
                _append_period_values(period, starts, ends)
                timezone = timezone or period.get("timezone")
            _append_period_values(row, starts, ends)
            timezone = timezone or row.get("period_timezone")
        start = min(starts) if starts else None
        end = max(ends) if ends else None
        return {
            "start": start,
            "end": end,
            "timezone": str(timezone) if timezone else None,
            "label": _period_label(start, end, str(timezone) if timezone else "CST"),
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

    def _card_widget(self, country: str, card_role: str) -> dict[str, Any] | None:
        rows = [
            *self.store.read_country_dataset(country, DATASET_SUMMARY_WIDGETS),
            *self.store.read_country_dataset(country, DATASET_ERRORS_WIDGETS),
        ]
        for row in rows:
            if row.get("card_role") == card_role and card_role in self._enabled_roles(country):
                return _widget_from_row(row)
        return None

    def _card_rows(self, country: str, card_role: str) -> list[dict[str, Any]]:
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
            for row in self.store.read_country_dataset(country, dataset)
            if row.get("card_role") == card_role and card_role in self._enabled_roles(country)
        ]

    def _enabled_roles(self, country: str) -> set[str]:
        if self.config_store is None:
            return set(required_roles())
        try:
            config = self.config_store.read()
            country_config = config.country_config(country)
        except Exception:
            return set(required_roles())
        if country_config is None:
            return set(required_roles())
        return set(country_config.enabled_widget_roles())


def _widget_from_row(row: dict[str, Any]) -> dict[str, Any]:
    period = {
        "start": _text(row.get("period_start")),
        "end": _text(row.get("period_end")),
        "timezone": _text(row.get("period_timezone")) or "CST",
    }
    period["label"] = _period_label(period["start"], period["end"], period["timezone"])
    if row.get("chart_type") == "donut":
        return {
            "id": row.get("id"),
            "role": row.get("card_role"),
            "title": row.get("title") or row.get("card_title"),
            "chart_type": "donut",
            "total": row.get("total"),
            "series": _list(row.get("series")),
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


def _apply_segment(rows: list[dict[str, Any]], segment: str | None) -> list[dict[str, Any]]:
    parsed = parse_segment(segment)
    if not parsed:
        return rows
    field, value = parsed
    if field == "error_state":
        return [
            row
            for row in rows
            if _metric_state(row.get("sessions_with_error") or row.get("error_sessions")) == value
        ]
    if field == "conversion_state":
        return [
            row
            for row in rows
            if ("converted" if _number(row.get("conversions")) > 0 else "not_converted") == value
        ]
    return [row for row in rows if str(row.get(field) or row.get("name") or "") == value]


def _metric_state(value: Any) -> str:
    parsed = value if isinstance(value, (int, float)) else None
    return "with_error" if parsed and parsed > 0 else "without_error"


def _selection(value: str | None) -> dict[str, str] | None:
    if not value:
        return None
    return {"id": value, "label": humanize_key(value)}


def _segment_selection(segment: str | None) -> dict[str, str] | None:
    parsed = parse_segment(segment)
    if not parsed:
        return None
    field, value = parsed
    return {"id": segment or "", "label": f"{humanize_key(field)}: {value}"}


def _summary_widgets_for_segment(
    widgets: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    segment: str,
) -> list[dict[str, Any]]:
    filtered = _apply_segment(rows, segment)
    totals = {
        "page_views": sum(_number(row.get("page_views")) for row in filtered),
        "sessions": sum(_number(row.get("sessions")) for row in filtered),
        "converted_sessions": sum(_number(row.get("conversions")) for row in filtered),
    }
    next_widgets = []
    for widget in widgets:
        next_widget = {**widget}
        if next_widget.get("id") in totals:
            next_widget["value"] = round(totals[str(next_widget["id"])], 2)
            next_widget["breakdown"] = []
            next_widget["timeseries"] = []
            next_widget["chart_payload"] = None
        next_widgets.append(next_widget)
    return next_widgets


def _error_widgets_for_segment(
    widgets: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    segment: str,
) -> list[dict[str, Any]]:
    filtered = _apply_segment(rows, segment)
    total_error_sessions = sum(_number(row.get("sessions_with_error")) for row in filtered)
    total_sessions = sum(_number(row.get("sessions")) for row in filtered)
    percent = round((total_error_sessions / total_sessions) * 100, 2) if total_sessions else 0.0
    next_widgets = []
    for widget in widgets:
        next_widget = {**widget}
        if next_widget.get("id") == "error_sessions_percentage_evolution":
            next_widget["value"] = percent
            next_widget["breakdown"] = []
            next_widget["timeseries"] = []
            next_widget["chart_payload"] = None
        elif next_widget.get("id") == "error_sessions_by_app_name":
            series: list[dict[str, str | float]] = [
                {
                    "name": str(row.get("name") or row.get("app_name") or "Null"),
                    "value": _number(row.get("sessions_with_error")),
                    "percent": _number(row.get("error_session_percent")),
                }
                for row in filtered
            ]
            next_widget["total"] = round(total_error_sessions, 2)
            next_widget["series"] = [item for item in series if float(item["value"]) > 0]
        next_widgets.append(next_widget)
    return next_widgets


def _number(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0


def _append_period_values(
    row: dict[str, Any],
    starts: list[str],
    ends: list[str],
) -> None:
    start = row.get("start") or row.get("period_start")
    end = row.get("end") or row.get("period_end")
    if start:
        starts.append(str(start))
    if end:
        ends.append(str(end))


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


def _period_label(start: Any, end: Any, timezone: str | None) -> str | None:
    zone_label = timezone or "CST"
    start_dt = parse_datetime(start, zone_label)
    end_dt = parse_datetime(end, zone_label)
    if start_dt is None and end_dt is None:
        return None
    start_dt = start_dt or end_dt
    end_dt = end_dt or start_dt
    if start_dt is None or end_dt is None:
        return None
    return format_period_label(start_dt, end_dt, zone_label)


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


def local_dashboard_root(store: ParquetStore, country: str) -> Path:
    return store.settings.parquet_dir / f"country={country}"
