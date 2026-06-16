import { ArrowDown, ArrowUp, Search } from "lucide-react";
import {
  ErrorPercentRow,
  ErrorTableResponse,
  SortDirection,
  TableColumn,
} from "../types";
import { EmptyAnalyticsState } from "./EmptyAnalyticsState";

type Props = {
  response?: ErrorTableResponse;
  isLoading: boolean;
  title?: string;
  searchLabel?: string;
  loadingLabel?: string;
  search: string;
  sort: string;
  direction: SortDirection;
  onSearchChange: (value: string) => void;
  onSortChange: (key: string) => void;
};

export function ErrorPercentageTable({
  response,
  isLoading,
  title = "% Sesiones con Error por App Name",
  searchLabel = "Buscar errores",
  loadingLabel = "Cargando errores",
  search,
  sort,
  direction,
  onSearchChange,
  onSortChange,
}: Props) {
  return (
    <section className="dashboard-card table-card">
      <div className="section-heading">
        <div>
          <h2>{title}</h2>
          <span>{response?.rows.length ?? 0} filas</span>
        </div>
        <label className="search-field compact">
          <Search size={16} aria-hidden="true" />
          <input
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Buscar"
            aria-label={searchLabel}
          />
        </label>
      </div>

      {isLoading ? (
        <div className="analytics-loading">{loadingLabel}</div>
      ) : response?.status === "ok" && response.rows.length ? (
        <div className="table-scroll">
          <table className="table dashboard-table">
            <thead>
              <tr>
                {response.columns.map((column) => (
                  <th key={column.key}>
                    {column.sortable ? (
                      <button onClick={() => onSortChange(column.key)}>
                        {column.label}
                        {sort === column.key &&
                          (direction === "asc" ? (
                            <ArrowUp size={14} />
                          ) : (
                            <ArrowDown size={14} />
                          ))}
                      </button>
                    ) : (
                      column.label
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {response.rows.map((row) => (
                <tr key={row.name}>
                  {response.columns.map((column) => (
                    <td key={column.key}>{renderCell(row, column)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyAnalyticsState
          reason={response?.reason}
          requiredDataset={response?.required_dataset}
        />
      )}
    </section>
  );
}

function renderCell(row: ErrorPercentRow, column: TableColumn) {
  const value = row[column.key as keyof ErrorPercentRow];
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") {
    const suffix = column.key.includes("percent") ? "%" : "";
    return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`;
  }
  return value;
}
