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

export type KpiWidget = {
  id: string;
  title: string;
  value?: number | null;
  unit: "count" | "seconds" | "percent";
  breakdown: KpiBreakdownItem[];
  timeseries: TimeseriesPoint[];
  comparison?: DashboardComparison | null;
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
  conversions_delta_percent?: number | null;
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
