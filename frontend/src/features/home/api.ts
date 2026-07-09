import { apiGet, apiPost } from "../../shared/api/client";
import {
  CountriesResponse,
  CountryCode,
  DashboardCoverage,
  DetailTableResponse,
  DynamicDashboardResponse,
  ErrorTableResponse,
  ErrorsDashboardResponse,
  SortDirection,
  SummaryDashboardResponse,
} from "./types";

type DashboardParams = {
  country: CountryCode;
  startDate?: string | null;
  endDate?: string | null;
  rangeKey?: string | null;
};

type TableParams = DashboardParams & {
  search?: string;
  sort: string;
  direction: SortDirection;
};

export function getCountries() {
  return apiGet<CountriesResponse>("/local-dashboard/countries");
}

export function getCoverage(params: DashboardParams) {
  return apiGet<DashboardCoverage>(
    `/local-dashboard/coverage?${toCoverageQuery(params)}`,
  );
}

export function ingestRange(
  country: CountryCode,
  range: Pick<DashboardParams, "rangeKey" | "startDate" | "endDate"> & {
    reason?: string | null;
  },
) {
  return apiPost("/ingestions/range", {
    country,
    range_key: range.rangeKey,
    start_date: range.startDate,
    end_date: range.endDate,
    reason: range.reason ?? "user_requested",
  });
}

export function getDashboard(params: DashboardParams) {
  return apiGet<DynamicDashboardResponse>(
    `/local-dashboard/dashboard?${toQuery(params)}`,
  );
}

export function getSummary(params: DashboardParams) {
  return apiGet<SummaryDashboardResponse>(
    `/local-dashboard/summary?${toQuery(params)}`,
  );
}

export function getSummaryTable(params: TableParams) {
  return apiGet<DetailTableResponse>(
    `/local-dashboard/summary/table?${toQuery(params)}`,
  );
}

export function getErrors(params: DashboardParams) {
  return apiGet<ErrorsDashboardResponse>(
    `/local-dashboard/errors?${toQuery(params)}`,
  );
}

export function getTopErrorsTable(params: TableParams) {
  return apiGet<ErrorTableResponse>(
    `/local-dashboard/errors/top-errors?${toQuery(params)}`,
  );
}

export function getErrorsAppNameTable(params: TableParams) {
  return apiGet<ErrorTableResponse>(
    `/local-dashboard/errors/app-name?${toQuery(params)}`,
  );
}

function toQuery(values: Record<string, string | null | undefined>) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      params.set(toSnakeCase(key), value);
    }
  });
  return params.toString();
}

function toCoverageQuery(params: DashboardParams) {
  return toQuery({
    country: params.country,
    start: params.startDate,
    end: params.endDate,
    rangeKey: params.rangeKey,
  });
}

function toSnakeCase(value: string) {
  return value.replace(/[A-Z]/g, (match) => `_${match.toLowerCase()}`);
}
