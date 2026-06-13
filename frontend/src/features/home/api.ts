import { apiGet } from "../../shared/api/client";
import {
  CountriesResponse,
  CountryCode,
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
};

type TableParams = DashboardParams & {
  search?: string;
  sort: string;
  direction: SortDirection;
};

export function getCountries() {
  return apiGet<CountriesResponse>("/analytics/countries");
}

export function getSummary(params: DashboardParams) {
  return apiGet<SummaryDashboardResponse>(
    `/analytics/dashboard/summary?${toQuery(params)}`,
  );
}

export function getSummaryTable(params: TableParams) {
  return apiGet<DetailTableResponse>(
    `/analytics/dashboard/summary/table?${toQuery(params)}`,
  );
}

export function getErrors(params: DashboardParams) {
  return apiGet<ErrorsDashboardResponse>(
    `/analytics/dashboard/errors?${toQuery(params)}`,
  );
}

export function getErrorsTable(params: TableParams) {
  return apiGet<ErrorTableResponse>(
    `/analytics/dashboard/errors/table?${toQuery(params)}`,
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
      params.set(key, value);
    }
  });
  return params.toString();
}
