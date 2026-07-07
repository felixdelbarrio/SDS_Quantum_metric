from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from backend.app.quantum_dashboard.catalog import spec_for_role
from backend.app.quantum_dashboard.generic_roles import (
    is_supported_generic_widget_type,
    normalized_widget_type,
)


class WidgetSupportAssessment(BaseModel):
    widget_id: str
    title: str
    widget_type: str
    visual_role: str | None
    supported: bool
    support_level: Literal["specific_role", "generic_type", "unsupported"]
    parser_name: str | None
    reason: str | None = None


PARSER_REGISTRY = {
    "specific": {
        "summary.page_views": "timeseries_metric_card_v1",
        "summary.sessions": "timeseries_metric_card_v1",
        "summary.converted_sessions": "timeseries_metric_card_v1",
        "summary.avg_session_duration": "timeseries_metric_card_v1",
        "summary.detail_by_app_name_os": "dimension_table_card_v1",
        "errors.error_sessions_percentage_evolution": "timeseries_metric_card_v1",
        "errors.top_errors_by_error_name": "top_errors_table_card_v1",
        "errors.error_sessions_by_app_name_comparison": "donut_distribution_card_v1",
        "errors.error_session_percentage_by_app_name": "percentage_table_card_v1",
    },
    "generic": {
        "CHART": "generic_metric_card_v1",
        "KPI": "generic_metric_card_v1",
        "TABLE": "generic_table_card_v1",
        "DONUT": "generic_donut_card_v1",
    },
}


def assess_widget_support(
    *,
    widget_id: str,
    title: str,
    widget_type: str | None,
    visual_role: str | None,
) -> WidgetSupportAssessment:
    role = visual_role or None
    spec = spec_for_role(role)
    if role and spec is not None and not role.startswith("generic."):
        return WidgetSupportAssessment(
            widget_id=widget_id,
            title=title,
            widget_type=normalized_widget_type(widget_type),
            visual_role=role,
            supported=True,
            support_level="specific_role",
            parser_name=spec.parse_strategy,
        )

    normalized_type = normalized_widget_type(widget_type)
    if is_supported_generic_widget_type(normalized_type):
        parser_name = PARSER_REGISTRY["generic"].get(normalized_type, "generic_metric_card_v1")
        return WidgetSupportAssessment(
            widget_id=widget_id,
            title=title,
            widget_type=normalized_type,
            visual_role=role,
            supported=True,
            support_level="generic_type",
            parser_name=parser_name,
        )

    return WidgetSupportAssessment(
        widget_id=widget_id,
        title=title,
        widget_type=normalized_type,
        visual_role=role,
        supported=False,
        support_level="unsupported",
        parser_name=None,
        reason=f"No parser registered for widget type {normalized_type}.",
    )
