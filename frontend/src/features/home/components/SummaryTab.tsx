import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getSummaryTable } from "../api";
import { DateRange } from "./DashboardHeader";
import { CountryCode, SortDirection, SummaryDashboardResponse } from "../types";
import { EmptyAnalyticsState } from "./EmptyAnalyticsState";
import { KpiWidget } from "./KpiWidget";
import { SummaryDetailTable } from "./SummaryDetailTable";

type Props = {
  country: CountryCode;
  dimension?: string | null;
  segment?: string | null;
  dateRange: DateRange;
  response?: SummaryDashboardResponse;
  isLoading: boolean;
};

export function SummaryTab({
  country,
  dimension,
  segment,
  dateRange,
  response,
  isLoading,
}: Props) {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("page_views");
  const [direction, setDirection] = useState<SortDirection>("desc");

  const table = useQuery({
    queryKey: [
      "dashboard",
      "summary-table",
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
      getSummaryTable({
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

  if (isLoading) {
    return <div className="analytics-loading">Cargando resumen</div>;
  }

  return (
    <div className="dashboard-tab-panel">
      {response?.status === "ok" && response.widgets.length ? (
        <section className="dashboard-widget-grid">
          {response.widgets.map((widget) => (
            <KpiWidget key={widget.id} widget={widget} />
          ))}
        </section>
      ) : (
        <EmptyAnalyticsState
          reason={response?.reason}
          requiredDataset={response?.required_dataset}
        />
      )}

      <SummaryDetailTable
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
