from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

type DashboardTab = Literal["summary", "errors"]
type ParseStrategy = Literal[
    "timeseries_metric_card_v1",
    "single_metric_breakdown_card_v1",
    "dimension_table_card_v1",
    "historical_comparison_card_v1",
    "donut_distribution_card_v1",
    "top_errors_table_card_v1",
    "percentage_table_card_v1",
]
type VisualRole = Literal[
    "summary.page_views",
    "summary.sessions",
    "summary.converted_sessions",
    "summary.avg_session_duration",
    "summary.detail_by_app_name_os",
    "errors.error_sessions_percentage_evolution",
    "errors.top_errors_by_error_name",
    "errors.error_sessions_by_app_name_comparison",
    "errors.error_session_percentage_by_app_name",
]
type RegressionStatus = Literal[
    "passed",
    "passed_with_tolerance",
    "failed_missing_card",
    "failed_missing_api_response",
    "failed_parse_error",
    "failed_value_mismatch",
    "failed_table_mismatch",
    "failed_chart_mismatch",
]
type RegressionVerdict = Literal["PASSED", "PASSED_WITH_TOLERANCE", "FAILED"]


class DashboardPeriod(BaseModel):
    start: str | None = None
    end: str | None = None
    timezone: str | None = None


class DashboardCardSpec(BaseModel):
    tab: DashboardTab
    role: VisualRole
    title: str
    card_type: str
    parse_strategy: ParseStrategy
    required: bool = True
    local_id: str
    unit: Literal["count", "seconds", "percent"] | None = None
    default_sort: str | None = None


class CardContract(BaseModel):
    country: str
    dashboard_id: str | None = None
    team_id: str | None = None
    tab: DashboardTab
    tab_name: str
    card_id: str
    card_title: str
    card_type: str
    visual_role: VisualRole
    source_endpoint: str
    request_hash: str
    response_hash: str
    metric_ids: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    period: DashboardPeriod = Field(default_factory=DashboardPeriod)
    parse_strategy: ParseStrategy
    chart_type: str | None = None
    columns: list[str] = Field(default_factory=list)
    measures: list[str] = Field(default_factory=list)
    required: bool = True
    discovered_at: str


class WebSnapshot(BaseModel):
    ingestion_id: str
    country: str
    dashboard_id: str | None = None
    team_id: str | None = None
    tab: DashboardTab
    card_role: VisualRole
    card_title: str
    visible_value: float | str | None = None
    visible_breakdowns: list[dict[str, Any]] = Field(default_factory=list)
    visible_series: list[dict[str, Any]] = Field(default_factory=list)
    visible_table_columns: list[str] = Field(default_factory=list)
    visible_table_rows: list[dict[str, Any]] = Field(default_factory=list)
    screenshot_path: str | None = None
    dom_snapshot_path: str | None = None
    captured_at: str


class ParserResult(BaseModel):
    role: VisualRole
    status: Literal["ok", "error"]
    data: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None


class DerivedBuildResult(BaseModel):
    ingestion_id: str | None = None
    country: str
    raw_calls: int
    raw_rows: int
    captured_cards: int
    mandatory_cards: int
    mandatory_cards_captured: int
    derived_datasets: int
    missing_roles: list[str] = Field(default_factory=list)
    parser_errors: list[dict[str, str]] = Field(default_factory=list)
    regression_status: RegressionStatus


class RegressionCardResult(BaseModel):
    tab: DashboardTab
    card_role: VisualRole
    card_title: str
    web_value: float | str | None = None
    local_value: float | str | None = None
    status: RegressionStatus
    difference: float | None = None
    details: str | None = None


class RegressionReport(BaseModel):
    ingestion_id: str | None = None
    country: str
    dashboard_id: str | None = None
    team_id: str | None = None
    tabs: list[DashboardTab]
    cards: list[RegressionCardResult]
    verdict: RegressionVerdict
    status: RegressionStatus
    tolerance_percent: float
    generated_at: str


class DashboardDiscoveryResult(BaseModel):
    country: str
    base_url: str
    dashboard_id: str | None = None
    team_id: str | None = None
    summary_tab: int = 0
    errors_tab: int = 1
    tabs: list[dict[str, Any]] = Field(default_factory=list)
    source: Literal["env", "url", "metadata", "default", "unresolved"] = "unresolved"
    message: str
