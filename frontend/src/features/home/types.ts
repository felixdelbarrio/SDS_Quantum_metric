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
  dashboard_id?: string | null;
  dashboard_name?: string | null;
  timezone: string;
};

export type CountriesResponse = {
  countries: AvailableCountry[];
  default_country: CountryCode;
};

export type DashboardCoverage = {
  country: CountryCode;
  dashboard_id?: string | null;
  start: string | null;
  end: string | null;
  range_key?: string;
  complete: boolean;
  completeness?: "complete" | "partial" | "empty";
  data_quality?:
    | "missing_days"
    | "range_mismatch"
    | "regression_failed"
    | "complete";
  warning_level?: "none" | "info" | "warning" | "error";
  last_regression_status?: "passed" | "failed" | "not_run";
  required_days?: string[];
  covered_days: string[];
  missing_days: string[];
  message: string;
};

export type KpiBreakdownItem = {
  label: string;
  value: number | null;
  display?: DisplayNumberContract | null;
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
  raw_delta?: number | null;
  display_delta?: number | null;
  precision?: number;
  formatted?: string | null;
  semantic_intent?: "positive" | "negative" | "neutral";
  delta_percent?: number | null;
};

export type DisplayNumberContract = {
  raw_value?: number | null;
  display_value?: number | null;
  unit: "count" | "score" | "percent" | "seconds" | "text";
  scale: number;
  precision: number;
  prefix?: string | null;
  suffix?: string | null;
  formatter?: string | null;
  formatted?: string | null;
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
  series_id?: string;
  id?: string;
  label: string;
  kind: "line" | "bar" | "area" | "baseline" | "band" | "anomaly";
  order?: number;
  device?: "mobile" | "desktop" | "unknown" | null;
  points: ChartSeriesPoint[];
  visible: boolean;
};

export type ChartBand = {
  band_id?: string;
  id?: string;
  label?: string | null;
  kind?: "historical_range" | "anomaly" | "confidence" | "custom";
  start?: string | null;
  end?: string | null;
  lower_points?: ChartSeriesPoint[];
  upper_points?: ChartSeriesPoint[];
  pattern?: string | null;
  start_ts?: string | null;
  end_ts?: string | null;
  start_x?: number | null;
  end_x?: number | null;
  value_min?: number | null;
  value_max?: number | null;
  purpose?: string | null;
};

export type ChartPayload = {
  chart_type: "line" | "bar" | "area" | "stacked_bar" | "donut" | "mixed";
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
  widget_id?: string | null;
  tab_name?: string | null;
  tab_index?: number | null;
  widget_order?: number | null;
  range_key?: string | null;
  title: string;
  display?: DisplayNumberContract | null;
  value?: number | null;
  unit?: "count" | "score" | "seconds" | "percent" | "text";
  chart_type?: "line" | "bar" | "donut" | "table" | null;
  breakdown: KpiBreakdownItem[];
  timeseries: TimeseriesPoint[];
  chart_payload?: ChartPayload | null;
  chart?: ChartPayload | null;
  table?: {
    columns: Array<{
      key: string;
      label: string;
      data_type: "text" | "number" | "percent" | "datetime";
      precision?: number | null;
      sortable: boolean;
      default_sort?: "asc" | "desc" | null;
    }>;
    rows: Array<Record<string, unknown>>;
    default_sort_column?: string | null;
    default_sort_direction?: "asc" | "desc" | null;
    period_label: string;
    timezone: string;
  } | null;
  table_columns?: string[] | null;
  table_rows?: Array<Record<string, unknown>> | null;
  comparison?: DashboardComparison | null;
  delta_percent?: number | null;
  semantic_state?: "positive" | "negative" | "neutral" | null;
  semantic_intent?: "good" | "bad" | "neutral" | null;
  missing_source_field?: string | null;
  period?: DashboardPeriod | null;
  layout_x?: number | null;
  layout_y?: number | null;
  layout_width?: number | null;
  layout_height?: number | null;
  parse_status?: string;
};

export type DynamicDashboardSection = {
  section_id?: string | null;
  section_name?: string | null;
  section_index?: number | null;
  widgets: KpiWidget[];
};

export type DynamicDashboardTab = {
  tab: string;
  tab_name: string;
  tab_index: number;
  tab_id?: string | null;
  sections: DynamicDashboardSection[];
  widgets?: KpiWidget[];
};

export type DynamicDashboardResponse = {
  status: AnalyticsStatus;
  country: CountryCode;
  source: "parquet";
  last_ingestion_at?: string | null;
  dashboard_id?: string | null;
  dashboard_name?: string | null;
  dashboard_title?: string | null;
  description?: string | null;
  tabs: DynamicDashboardTab[];
  reason?: string | null;
  required_dataset?: string | null;
  available_datasets: string[];
  period?: DashboardPeriod;
  regression?: DashboardRegression | null;
};

export type SummaryDashboardResponse = {
  status: AnalyticsStatus;
  country: CountryCode;
  source: "parquet";
  last_ingestion_at?: string | null;
  dashboard_id?: string | null;
  dashboard_name?: string | null;
  dashboard_title?: string | null;
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
  children_count?: number | null;
};

export type DetailTableResponse = {
  status: AnalyticsStatus;
  country: CountryCode;
  columns: TableColumn[];
  rows: DetailTableRow[];
  source: "parquet";
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
  range_key?: string | null;
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
  dashboard_id?: string | null;
  dashboard_name?: string | null;
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
  reason?: string | null;
  required_dataset?: string | null;
  available_datasets: string[];
};

export type DashboardRegression = {
  status?: string | null;
  verdict?: string | null;
  report?: string | null;
};
