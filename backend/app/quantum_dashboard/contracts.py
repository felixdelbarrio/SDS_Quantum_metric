from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.app.quantum_dashboard.models import ChartAxis, ChartSeriesPoint

type ResolutionStatus = Literal["resolved", "missing", "ambiguous", "invalid"]
type ParseStatus = Literal[
    "resolved",
    "failed_missing_primary_value",
    "failed_ambiguous_primary_value",
    "failed_missing_table_contract",
    "failed_invalid_table_contract",
    "failed_missing_chart_contract",
    "failed_invalid_chart_contract",
    "failed_invalid_contract",
    "failed_ambiguous_widget_correlation",
]
PARSE_STATUSES: set[str] = {
    "resolved",
    "failed_missing_primary_value",
    "failed_ambiguous_primary_value",
    "failed_missing_table_contract",
    "failed_invalid_table_contract",
    "failed_missing_chart_contract",
    "failed_invalid_chart_contract",
    "failed_invalid_contract",
    "failed_ambiguous_widget_correlation",
}
type DisplayUnit = Literal["count", "score", "percent", "seconds", "text"]
type SemanticIntent = Literal["positive", "negative", "neutral"]
type SeriesKind = Literal["line", "bar", "area", "baseline", "band", "anomaly"]
type ChartType = Literal["line", "bar", "area", "stacked_bar", "donut", "mixed"]
type SortDirection = Literal["asc", "desc"]
type TableDataType = Literal["text", "number", "percent", "datetime"]


class ContractResolution(BaseModel):
    status: ResolutionStatus
    value: Any | None = None
    evidence: list[str] = Field(default_factory=list)
    error: str | None = None


class DisplayNumberContract(BaseModel):
    raw_value: float | int | None = None
    display_value: float | int | None = None
    unit: DisplayUnit
    scale: float = 1
    precision: int = Field(ge=0)
    prefix: str | None = None
    suffix: str | None = None
    formatter: str | None = None
    formatted: str | None = None


class HistoricalComparisonContract(BaseModel):
    label: str
    raw_delta: float | None = None
    display_delta: float | None = None
    precision: int = Field(ge=0)
    formatted: str | None = None
    semantic_intent: SemanticIntent


class QuantumSeriesContract(BaseModel):
    series_id: str
    label: str
    kind: SeriesKind
    order: int = Field(ge=0)
    points: list[ChartSeriesPoint] = Field(default_factory=list)
    visible: bool = True
    style: str | None = None


class QuantumBandContract(BaseModel):
    band_id: str
    label: str
    kind: Literal["historical_range", "anomaly", "confidence", "custom"]
    start: str | None = None
    end: str | None = None
    lower_points: list[ChartSeriesPoint] = Field(default_factory=list)
    upper_points: list[ChartSeriesPoint] = Field(default_factory=list)
    pattern: str | None = None


class ChartLegendContract(BaseModel):
    id: str
    label: str
    order: int = Field(ge=0)
    kind: SeriesKind | None = None
    visible: bool = True


class QuantumChartContract(BaseModel):
    chart_type: ChartType
    x_axis: ChartAxis
    y_axis: ChartAxis
    series: list[QuantumSeriesContract] = Field(default_factory=list)
    bands: list[QuantumBandContract] = Field(default_factory=list)
    legends: list[ChartLegendContract] = Field(default_factory=list)
    period_label: str
    timezone: str
    granularity: str


class QuantumTableColumnContract(BaseModel):
    key: str
    label: str
    data_type: TableDataType
    precision: int | None = Field(default=None, ge=0)
    sortable: bool = False
    default_sort: SortDirection | None = None


class QuantumTableContract(BaseModel):
    columns: list[QuantumTableColumnContract] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    default_sort_column: str | None = None
    default_sort_direction: SortDirection | None = None
    period_label: str
    timezone: str


class QuantumWidgetContract(BaseModel):
    schema_version: int = 3
    country: str
    dashboard_id: str
    dashboard_name: str
    tab_id: str | None = None
    tab_name: str
    tab_index: int = Field(ge=0)
    section_id: str | None = None
    section_name: str | None = None
    section_index: int | None = Field(default=None, ge=0)
    widget_id: str
    card_id: str | None = None
    visual_role: str
    widget_title: str
    widget_type: str
    widget_order: int = Field(ge=0)
    layout_x: int | None = None
    layout_y: int | None = None
    layout_width: int | None = Field(default=None, ge=1)
    layout_height: int | None = Field(default=None, ge=1)
    value: DisplayNumberContract | None = None
    comparison: HistoricalComparisonContract | None = None
    chart: QuantumChartContract | None = None
    table: QuantumTableContract | None = None
    range_key: str
    requested_start: str
    requested_end: str
    effective_start: str
    effective_end: str
    period_label: str
    timezone: str
    query_period: str | None = None
    request_hash: str
    response_hash: str
    query_hash: str | None = None
    parser_version: str
    parse_status: ParseStatus = "resolved"

    def storage_row(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload.update(
            {
                "card_role": self.visual_role,
                "card_title": self.widget_title,
                "chart_type": self.chart.chart_type
                if self.chart
                else "table"
                if self.table
                else "kpi",
                "formatted_value": self.value.formatted if self.value else None,
            }
        )
        return payload
