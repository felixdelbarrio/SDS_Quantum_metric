import type { CountryCode } from "../../shared/countries";

export type { CountryCode };

export type AnalyticsStatus = "ok" | "empty";
export type SortDirection = "asc" | "desc";

export type AvailableCountry = {
  code: CountryCode;
  label: string;
  has_data: boolean;
  raw_calls: number;
  rows: number;
  cards?: number;
  regression_status?: string | null;
  last_ingestion_at?: string | null;
};

export type CountriesResponse = {
  countries: AvailableCountry[];
  default_country: CountryCode;
};

export type DashboardCoverage = {
  country: CountryCode;
  start: string | null;
  end: string | null;
  range_key?: string;
  complete: boolean;
  completeness?: "complete" | "partial" | "empty";
  warning_level?: "none" | "info" | "warning" | "blocking";
  required_days?: string[];
  covered_days: string[];
  missing_days: string[];
  message: string;
};

export type DashboardSelection = {
  id: string;
  label: string;
};

export type DashboardDimension = {
  id: string;
  label: string;
  status: "available" | "insufficient_data";
};

export type DashboardDimensionGroup = {
  label: string;
  items: DashboardDimension[];
};

export type DimensionsResponse = {
  country: CountryCode;
  groups: DashboardDimensionGroup[];
};

export type DashboardSegment = {
  id: string;
  label: string;
  field: string;
  value: string;
  count: number;
};

export type SegmentsResponse = {
  country: CountryCode;
  segments: DashboardSegment[];
};

export type KpiBreakdownItem = {
  label: string;
  value: number;
};

export type TimeseriesPoint = {
  ts: string;
  value: number;
};

export type DashboardPeriod = {
  start?: string | null;
  end?: string | null;
  timezone?: string | null;
  label?: string | null;
};

export type DashboardComparison = {
  label: string;
  delta_percent?: number | null;
};

export type ChartAxisTick = {
  value: number | string;
  label: string;
  position?: number | null;
};

export type ChartAxis = {
  min?: number | null;
  max?: number | null;
  unit?: string | null;
  ticks: ChartAxisTick[];
  label?: string | null;
};

export type ChartSeriesPoint = {
  ts?: string | null;
  label?: string | null;
  value?: number | null;
  raw_value?: number | null;
  x?: number | null;
  y?: number | null;
};

export type ChartSeries = {
  id: string;
  label: string;
  kind: "line" | "bar" | "area";
  device?: "mobile" | "desktop" | "unknown" | null;
  points: ChartSeriesPoint[];
  visible: boolean;
};

export type ChartBand = {
  id: string;
  label?: string | null;
  start_ts?: string | null;
  end_ts?: string | null;
  start_x?: number | null;
  end_x?: number | null;
  value_min?: number | null;
  value_max?: number | null;
  purpose?: string | null;
};

export type ChartPayload = {
  chart_type: "line" | "bar" | "donut" | "table";
  x_axis: ChartAxis;
  y_axis: ChartAxis;
  series: ChartSeries[];
  bands: ChartBand[];
  legends: Array<Record<string, unknown>>;
  period_label?: string | null;
  granularity?: string | null;
  timezone?: string | null;
};

export type KpiWidget = {
  id: string;
  role?: string;
  title: string;
  value?: number | null;
  unit: "count" | "seconds" | "percent";
  breakdown: KpiBreakdownItem[];
  timeseries: TimeseriesPoint[];
  chart_payload?: ChartPayload | null;
  comparison?: DashboardComparison | null;
  delta_percent?: number | null;
  semantic_state?: "positive" | "negative" | "neutral" | null;
  semantic_intent?: "good" | "bad" | "neutral" | null;
  missing_source_field?: string | null;
  period?: DashboardPeriod | null;
};

export type SummaryDashboardResponse = {
  status: AnalyticsStatus;
  country: CountryCode;
  source: "parquet";
  last_ingestion_at?: string | null;
  applied_dimension?: DashboardSelection | null;
  applied_segment?: DashboardSelection | null;
  widgets: KpiWidget[];
  reason?: string | null;
  required_dataset?: string | null;
  available_datasets: string[];
  period?: DashboardPeriod;
  regression?: DashboardRegression | null;
};

export type TableColumn = {
  key: string;
  label: string;
  sortable: boolean;
};

export type DetailTableRow = {
  name: string;
  app_name?: string | null;
  operating_system?: string | null;
  page_views?: number | null;
  sessions?: number | null;
  conversions?: number | null;
  page_views_delta_percent?: number | null;
  sessions_delta_percent?: number | null;
  conversions_delta_percent?: number | null;
  page_views_semantic_state?: "positive" | "negative" | "neutral" | null;
  sessions_semantic_state?: "positive" | "negative" | "neutral" | null;
  conversions_semantic_state?: "positive" | "negative" | "neutral" | null;
  row_id?: string | null;
  parent_row_id?: string | null;
  depth?: number | null;
  is_expandable?: boolean | null;
  is_expanded_default?: boolean | null;
};

export type DetailTableResponse = {
  status: AnalyticsStatus;
  country: CountryCode;
  columns: TableColumn[];
  rows: DetailTableRow[];
  source: "parquet";
  applied_dimension?: DashboardSelection | null;
  applied_segment?: DashboardSelection | null;
  reason?: string | null;
  required_dataset?: string | null;
  available_datasets: string[];
};

export type ErrorSeriesPoint = {
  name: string;
  value: number;
  percent: number;
};

export type ErrorPercentRow = {
  name: string;
  error_name?: string | null;
  app_name?: string | null;
  sessions?: number | null;
  error_sessions?: number | null;
  sessions_with_error?: number | null;
  error_session_percent?: number | null;
};

export type ErrorComparisonWidget = {
  id: string;
  role?: string;
  title: string;
  chart_type: "donut";
  total?: number | null;
  series: ErrorSeriesPoint[];
  chart_payload?: ChartPayload | null;
  comparison?: DashboardComparison | null;
  period?: DashboardPeriod | null;
};

export type ErrorPercentageWidget = {
  id: string;
  role?: string;
  title: string;
  chart_type: "table";
  rows: ErrorPercentRow[];
};

export type ErrorWidget =
  | ErrorComparisonWidget
  | ErrorPercentageWidget
  | KpiWidget;

export type ErrorsDashboardResponse = {
  status: AnalyticsStatus;
  country: CountryCode;
  source: "parquet";
  last_ingestion_at?: string | null;
  applied_dimension?: DashboardSelection | null;
  applied_segment?: DashboardSelection | null;
  widgets: ErrorWidget[];
  reason?: string | null;
  required_dataset?: string | null;
  available_datasets: string[];
  period?: DashboardPeriod;
  regression?: DashboardRegression | null;
};

export type ErrorTableResponse = {
  status: AnalyticsStatus;
  country: CountryCode;
  columns: TableColumn[];
  rows: ErrorPercentRow[];
  source: "parquet";
  applied_dimension?: DashboardSelection | null;
  applied_segment?: DashboardSelection | null;
  reason?: string | null;
  required_dataset?: string | null;
  available_datasets: string[];
};

export type DashboardRegression = {
  status?: string | null;
  verdict?: string | null;
  report?: string | null;
};
