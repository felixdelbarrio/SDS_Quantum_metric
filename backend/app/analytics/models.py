from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AnalyticsStatus = Literal["ok", "empty"]
SortDirection = Literal["asc", "desc"]


class AvailableCountry(BaseModel):
    code: str
    label: str
    has_data: bool
    raw_calls: int = 0
    rows: int = 0
    last_ingestion_at: str | None = None


class DashboardCountrySelection(BaseModel):
    countries: list[AvailableCountry]
    default_country: str


class DashboardFilter(BaseModel):
    field: str
    value: str


class DashboardDimension(BaseModel):
    id: str
    label: str
    status: Literal["available", "insufficient_data"] = "available"


class DashboardDimensionGroup(BaseModel):
    label: str
    items: list[DashboardDimension] = Field(default_factory=list)


class DashboardDimensionsResponse(BaseModel):
    country: str
    groups: list[DashboardDimensionGroup]


class DashboardSegment(BaseModel):
    id: str
    label: str
    field: str
    value: str
    count: int


class DashboardSegmentsResponse(BaseModel):
    country: str
    segments: list[DashboardSegment]


DashboardTab = Literal["summary", "errors"]


class DashboardSelection(BaseModel):
    id: str
    label: str


class KpiBreakdownItem(BaseModel):
    label: str
    value: float


class DashboardComparison(BaseModel):
    label: str
    delta_percent: float | None = None


class TimeseriesPoint(BaseModel):
    ts: str
    value: float


class KpiWidget(BaseModel):
    id: str
    title: str
    value: float | None = None
    unit: Literal["count", "seconds", "percent"] = "count"
    breakdown: list[KpiBreakdownItem] = Field(default_factory=list)
    timeseries: list[TimeseriesPoint] = Field(default_factory=list)
    comparison: DashboardComparison | None = None
    missing_source_field: str | None = None


class EmptyAnalyticsResponse(BaseModel):
    status: Literal["empty"] = "empty"
    country: str
    source: Literal["parquet"] = "parquet"
    reason: str
    required_dataset: str
    available_datasets: list[str] = Field(default_factory=list)
    rows: list[dict[str, object]] = Field(default_factory=list)
    metrics: None = None


class SummaryDashboardResponse(BaseModel):
    status: AnalyticsStatus
    country: str
    source: Literal["parquet"] = "parquet"
    last_ingestion_at: str | None = None
    applied_dimension: DashboardSelection | None = None
    applied_segment: DashboardSelection | None = None
    widgets: list[KpiWidget] = Field(default_factory=list)
    reason: str | None = None
    required_dataset: str | None = None
    available_datasets: list[str] = Field(default_factory=list)


class TableColumn(BaseModel):
    key: str
    label: str
    sortable: bool = True


class DetailTableRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    app_name: str | None = None
    operating_system: str | None = None
    page_views: float | None = None
    sessions: float | None = None
    conversions: float | None = None
    page_views_delta_percent: float | None = None
    conversions_delta_percent: float | None = None


class DetailTableResponse(BaseModel):
    status: AnalyticsStatus
    country: str
    columns: list[TableColumn] = Field(default_factory=list)
    rows: list[DetailTableRow] = Field(default_factory=list)
    source: Literal["parquet"] = "parquet"
    applied_dimension: DashboardSelection | None = None
    applied_segment: DashboardSelection | None = None
    reason: str | None = None
    required_dataset: str | None = None
    available_datasets: list[str] = Field(default_factory=list)


class ErrorSeriesPoint(BaseModel):
    name: str
    value: float
    percent: float


class ErrorPercentRow(BaseModel):
    name: str
    app_name: str | None = None
    sessions: float | None = None
    sessions_with_error: float | None = None
    error_session_percent: float | None = None


class ErrorComparisonWidget(BaseModel):
    id: str
    title: str
    chart_type: Literal["donut"]
    total: float | None = None
    series: list[ErrorSeriesPoint] = Field(default_factory=list)
    comparison: DashboardComparison | None = None


class ErrorPercentageWidget(BaseModel):
    id: str
    title: str
    chart_type: Literal["table"]
    rows: list[ErrorPercentRow] = Field(default_factory=list)


class ErrorsDashboardResponse(BaseModel):
    status: AnalyticsStatus
    country: str
    source: Literal["parquet"] = "parquet"
    last_ingestion_at: str | None = None
    applied_dimension: DashboardSelection | None = None
    applied_segment: DashboardSelection | None = None
    widgets: list[ErrorComparisonWidget | ErrorPercentageWidget] = Field(default_factory=list)
    reason: str | None = None
    required_dataset: str | None = None
    available_datasets: list[str] = Field(default_factory=list)


class ErrorComparisonResponse(BaseModel):
    status: AnalyticsStatus
    country: str
    columns: list[TableColumn] = Field(default_factory=list)
    rows: list[ErrorPercentRow] = Field(default_factory=list)
    source: Literal["parquet"] = "parquet"
    applied_dimension: DashboardSelection | None = None
    applied_segment: DashboardSelection | None = None
    reason: str | None = None
    required_dataset: str | None = None
    available_datasets: list[str] = Field(default_factory=list)
