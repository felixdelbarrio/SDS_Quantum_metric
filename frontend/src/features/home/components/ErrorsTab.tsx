import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getErrorsAppNameTable, getTopErrorsTable } from "../api";
import { DateRange } from "./DashboardHeader";
import {
  CountryCode,
  ErrorComparisonWidget,
  ErrorsDashboardResponse,
  ErrorTableResponse,
  KpiWidget as KpiWidgetType,
  SortDirection,
} from "../types";
import { EmptyAnalyticsState } from "./EmptyAnalyticsState";
import { ErrorDonut } from "./ErrorDonut";
import { ErrorPercentageTable } from "./ErrorPercentageTable";
import { KpiWidget } from "./KpiWidget";

type Props = {
  country: CountryCode;
  dimension?: string | null;
  segment?: string | null;
  dateRange: DateRange;
  response?: ErrorsDashboardResponse;
  isLoading: boolean;
};

export function ErrorsTab({
  country,
  dimension,
  segment,
  dateRange,
  response,
  isLoading,
}: Props) {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("error_session_percent");
  const [direction, setDirection] = useState<SortDirection>("desc");
  const [topSearch, setTopSearch] = useState("");
  const [topSort, setTopSort] = useState("error_sessions");
  const [topDirection, setTopDirection] = useState<SortDirection>("desc");

  const topErrors = useQuery<ErrorTableResponse>({
    queryKey: [
      "dashboard",
      "errors-top-table",
      country,
      dimension,
      segment,
      dateRange.startDate,
      dateRange.endDate,
      topSearch,
      topSort,
      topDirection,
    ],
    queryFn: () =>
      getTopErrorsTable({
        country,
        dimension,
        segment,
        startDate: dateRange.startDate,
        endDate: dateRange.endDate,
        search: topSearch,
        sort: topSort,
        direction: topDirection,
      }),
  });

  const table = useQuery<ErrorTableResponse>({
    queryKey: [
      "dashboard",
      "errors-app-table",
      country,
      dimension,
      segment,
      dateRange.startDate,
      dateRange.endDate,
      search,
      sort,
      direction,
    ],
    queryFn: () =>
      getErrorsAppNameTable({
        country,
        dimension,
        segment,
        startDate: dateRange.startDate,
        endDate: dateRange.endDate,
        search,
        sort,
        direction,
      }),
  });

  function handleSort(nextSort: string) {
    if (nextSort === sort) {
      setDirection((current) => (current === "asc" ? "desc" : "asc"));
    } else {
      setSort(nextSort);
      setDirection("desc");
    }
  }

  function handleTopSort(nextSort: string) {
    if (nextSort === topSort) {
      setTopDirection((current) => (current === "asc" ? "desc" : "asc"));
    } else {
      setTopSort(nextSort);
      setTopDirection("desc");
    }
  }

  const evolution = response?.widgets.find(
    (widget): widget is KpiWidgetType =>
      widget.id === "error_sessions_percentage_evolution",
  );
  const donut = response?.widgets.find(
    (widget): widget is ErrorComparisonWidget =>
      widget.id === "error_sessions_by_app_name",
  );

  if (isLoading) {
    return <div className="analytics-loading">Cargando errores</div>;
  }

  return (
    <div className="dashboard-tab-panel">
      {response?.status === "ok" && evolution ? (
        <section className="dashboard-widget-grid single">
          <KpiWidget widget={evolution} />
        </section>
      ) : (
        <EmptyAnalyticsState
          reason={response?.reason}
          requiredDataset={response?.required_dataset}
        />
      )}
      <ErrorPercentageTable
        title="Top 10 Errores por nombre del error"
        searchLabel="Buscar top errores"
        loadingLabel="Cargando top errores"
        response={topErrors.data}
        isLoading={topErrors.isLoading}
        search={topSearch}
        sort={topSort}
        direction={topDirection}
        onSearchChange={setTopSearch}
        onSortChange={handleTopSort}
      />
      {response?.status === "ok" && donut ? (
        <ErrorDonut widget={donut} />
      ) : (
        <EmptyAnalyticsState
          reason={response?.reason}
          requiredDataset={response?.required_dataset}
        />
      )}
      <ErrorPercentageTable
        response={table.data}
        isLoading={table.isLoading}
        search={search}
        sort={sort}
        direction={direction}
        onSearchChange={setSearch}
        onSortChange={handleSort}
      />
    </div>
  );
}
