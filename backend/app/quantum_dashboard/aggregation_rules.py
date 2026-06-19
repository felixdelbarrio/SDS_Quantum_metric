from __future__ import annotations

from typing import Literal

from backend.app.quantum_dashboard.models import VisualRole

MetricAggregation = Literal[
    "sum",
    "weighted_average",
    "ratio",
    "quantum_range_contract_required",
    "non_aggregable",
]

_ROLE_RULES: dict[str, MetricAggregation] = {
    "summary.page_views": "sum",
    "summary.sessions": "sum",
    "summary.converted_sessions": "quantum_range_contract_required",
    "summary.avg_session_duration": "weighted_average",
    "summary.detail_by_app_name_os": "quantum_range_contract_required",
    "errors.error_sessions_percentage_evolution": "ratio",
    "errors.top_errors_by_error_name": "quantum_range_contract_required",
    "errors.error_sessions_by_app_name_comparison": "quantum_range_contract_required",
    "errors.error_session_percentage_by_app_name": "quantum_range_contract_required",
}


def aggregation_for_role(role: str | VisualRole) -> MetricAggregation:
    return _ROLE_RULES.get(str(role), "non_aggregable")


def requires_quantum_range_contract(role: str | VisualRole) -> bool:
    return aggregation_for_role(role) == "quantum_range_contract_required"


def aggregation_rules() -> dict[str, MetricAggregation]:
    return dict(_ROLE_RULES)
