import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getErrorsTable } from "../api";
import {
  CountryCode,
  ErrorComparisonWidget,
  ErrorsDashboardResponse,
  ErrorTableResponse,
  SortDirection,
} from "../types";
import { EmptyAnalyticsState } from "./EmptyAnalyticsState";
import { ErrorDonut } from "./ErrorDonut";
import { ErrorPercentageTable } from "./ErrorPercentageTable";

type Props = {
  country: CountryCode;
  dimension?: string | null;
  segment?: string | null;
  response?: ErrorsDashboardResponse;
  isLoading: boolean;
};

export function ErrorsTab({
  country,
  dimension,
  segment,
  response,
  isLoading,
}: Props) {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("error_session_percent");
  const [direction, setDirection] = useState<SortDirection>("desc");

  const table = useQuery<ErrorTableResponse>({
    queryKey: [
      "dashboard",
      "errors-table",
      country,
      dimension,
      segment,
      search,
      sort,
      direction,
    ],
    queryFn: () =>
      getErrorsTable({
        country,
        dimension,
        segment,
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

  const donut = response?.widgets.find(
    (widget): widget is ErrorComparisonWidget =>
      widget.id === "error_sessions_by_app_name",
  );

  if (isLoading) {
    return <div className="analytics-loading">Cargando errores</div>;
  }

  return (
    <div className="dashboard-tab-panel">
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
