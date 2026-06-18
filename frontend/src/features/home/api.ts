import { apiGet, apiPost } from "../../shared/api/client";
import {
  CountriesResponse,
  CountryCode,
  DashboardCoverage,
  DetailTableResponse,
  DimensionsResponse,
  ErrorTableResponse,
  ErrorsDashboardResponse,
  SegmentsResponse,
  SortDirection,
  SummaryDashboardResponse,
} from "./types";

type DashboardParams = {
  country: CountryCode;
  dimension?: string | null;
  segment?: string | null;
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

export function ingestMissingDays(country: CountryCode, days: string[]) {
  return apiPost("/ingestions/missing-days", { country, days });
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

export function getDimensions(country: CountryCode) {
  return apiGet<DimensionsResponse>(
    `/analytics/dimensions?${toQuery({ country })}`,
  );
}

export function getSegments(country: CountryCode) {
  return apiGet<SegmentsResponse>(
    `/analytics/segments?${toQuery({ country })}`,
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
