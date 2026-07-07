from __future__ import annotations

from backend.app.quantum_dashboard.generic_roles import generic_kind_from_role, is_generic_role
from backend.app.quantum_dashboard.models import (
    DashboardCardSpec,
    DashboardTab,
    ParseStrategy,
    VisualRole,
)

SUMMARY_PAGE_VIEWS: VisualRole = "summary.page_views"
SUMMARY_SESSIONS: VisualRole = "summary.sessions"
SUMMARY_CONVERTED_SESSIONS: VisualRole = "summary.converted_sessions"
SUMMARY_AVG_SESSION_DURATION: VisualRole = "summary.avg_session_duration"
SUMMARY_DETAIL_TABLE: VisualRole = "summary.detail_by_app_name_os"
ERRORS_EVOLUTION: VisualRole = "errors.error_sessions_percentage_evolution"
ERRORS_TOP_ERRORS: VisualRole = "errors.top_errors_by_error_name"
ERRORS_APP_COMPARISON: VisualRole = "errors.error_sessions_by_app_name_comparison"
ERRORS_APP_PERCENTAGE: VisualRole = "errors.error_session_percentage_by_app_name"

MANDATORY_CARDS: tuple[DashboardCardSpec, ...] = (
    DashboardCardSpec(
        tab="summary",
        role=SUMMARY_PAGE_VIEWS,
        title="Paginas vistas",
        card_type="CHART",
        parse_strategy="timeseries_metric_card_v1",
        local_id="page_views",
        unit="count",
    ),
    DashboardCardSpec(
        tab="summary",
        role=SUMMARY_SESSIONS,
        title="Sesiones",
        card_type="CHART",
        parse_strategy="timeseries_metric_card_v1",
        local_id="sessions",
        unit="count",
    ),
    DashboardCardSpec(
        tab="summary",
        role=SUMMARY_CONVERTED_SESSIONS,
        title="Sesiones con conversion",
        card_type="CHART",
        parse_strategy="timeseries_metric_card_v1",
        local_id="converted_sessions",
        unit="count",
    ),
    DashboardCardSpec(
        tab="summary",
        role=SUMMARY_AVG_SESSION_DURATION,
        title="Tiempo medio de sesion",
        card_type="CHART",
        parse_strategy="timeseries_metric_card_v1",
        local_id="avg_session_duration",
        unit="seconds",
    ),
    DashboardCardSpec(
        tab="summary",
        role=SUMMARY_DETAIL_TABLE,
        title="Detalle por APP Name y Sistema operativo",
        card_type="TABLE",
        parse_strategy="dimension_table_card_v1",
        local_id="summary_detail_table",
        default_sort="page_views",
    ),
    DashboardCardSpec(
        tab="errors",
        role=ERRORS_EVOLUTION,
        title="Evolutivo - % Sesiones con Error",
        card_type="CHART",
        parse_strategy="timeseries_metric_card_v1",
        local_id="error_sessions_percentage_evolution",
        unit="percent",
    ),
    DashboardCardSpec(
        tab="errors",
        role=ERRORS_TOP_ERRORS,
        title="Top 20 Errores por nombre del error",
        card_type="TABLE",
        parse_strategy="top_errors_table_card_v1",
        local_id="errors_top_errors_table",
        default_sort="error_sessions",
    ),
    DashboardCardSpec(
        tab="errors",
        role=ERRORS_APP_COMPARISON,
        title="Comparativa de sesiones con error por App Name",
        card_type="DONUT",
        parse_strategy="donut_distribution_card_v1",
        local_id="error_sessions_by_app_name",
    ),
    DashboardCardSpec(
        tab="errors",
        role=ERRORS_APP_PERCENTAGE,
        title="% Sesiones con Error por App Name",
        card_type="TABLE",
        parse_strategy="percentage_table_card_v1",
        local_id="error_session_percentage_by_app_name",
        default_sort="error_session_percent",
    ),
)

ROLE_SPECS = {card.role: card for card in MANDATORY_CARDS}


def spec_for_role(role: str | None) -> DashboardCardSpec | None:
    if role is None:
        return None
    for visual_role, spec in ROLE_SPECS.items():
        if visual_role == role:
            return spec
    if is_generic_role(role):
        kind = generic_kind_from_role(role) or "CHART"
        strategy: ParseStrategy
        if kind == "TABLE":
            strategy = "generic_table_card_v1"
            card_type = "TABLE"
        elif kind == "DONUT":
            strategy = "generic_donut_card_v1"
            card_type = "DONUT"
        else:
            strategy = "generic_metric_card_v1"
            card_type = "CHART"
        return DashboardCardSpec(
            tab="summary",
            role=role,
            title=role,
            card_type=card_type,
            parse_strategy=strategy,
            local_id=role,
            unit="count",
            required=True,
        )
    return None


def required_roles(tab: DashboardTab | None = None) -> list[VisualRole]:
    return [card.role for card in MANDATORY_CARDS if tab is None or card.tab == tab]


def role_tab(role: VisualRole) -> DashboardTab:
    spec = spec_for_role(role)
    return spec.tab if spec is not None else "summary"
