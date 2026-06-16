import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  ChevronDown,
  Search,
} from "lucide-react";
import { useMemo, useState } from "react";
import {
  DetailTableResponse,
  DetailTableRow,
  SortDirection,
  TableColumn,
} from "../types";
import { EmptyAnalyticsState } from "./EmptyAnalyticsState";

type Props = {
  response?: DetailTableResponse;
  isLoading: boolean;
  search: string;
  sort: string;
  direction: SortDirection;
  onSearchChange: (value: string) => void;
  onSortChange: (key: string) => void;
};

export function SummaryDetailTable({
  response,
  isLoading,
  search,
  sort,
  direction,
  onSearchChange,
  onSortChange,
}: Props) {
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const rows = useMemo(() => response?.rows ?? [], [response?.rows]);
  const defaultExpanded = useMemo(
    () =>
      new Set(
        rows
          .filter((row) => row.is_expanded_default && row.row_id)
          .map((row) => String(row.row_id)),
      ),
    [rows],
  );
  const activeExpanded = expandedRows.size ? expandedRows : defaultExpanded;
  const visibleRows = rows.filter(
    (row) =>
      !row.parent_row_id || activeExpanded.has(String(row.parent_row_id)),
  );

  function toggleRow(rowId: string) {
    setExpandedRows((current) => {
      const next = new Set(current.size ? current : defaultExpanded);
      if (next.has(rowId)) next.delete(rowId);
      else next.add(rowId);
      return next;
    });
  }

  return (
    <section className="dashboard-card table-card">
      <div className="section-heading">
        <div>
          <h2>Detalle por App Name y Sistema operativo</h2>
          <span>{visibleRows.length} filas</span>
        </div>
        <label className="search-field compact">
          <Search size={16} aria-hidden="true" />
          <input
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Buscar"
            aria-label="Buscar en detalle"
          />
        </label>
      </div>

      {isLoading ? (
        <div className="analytics-loading">Cargando tabla</div>
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
              {visibleRows.map((row) => (
                <tr
                  key={
                    row.row_id ??
                    `${row.name}-${row.operating_system ?? "none"}`
                  }
                  className={row.depth ? "table-row-child" : "table-row-parent"}
                >
                  {response.columns.map((column) => (
                    <td key={column.key}>
                      {renderCell(row, column, toggleRow, activeExpanded)}
                    </td>
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

function renderCell(
  row: DetailTableRow,
  column: TableColumn,
  toggleRow: (rowId: string) => void,
  expandedRows: Set<string>,
) {
  const value = row[column.key as keyof DetailTableRow];
  if (column.key === "name") {
    const rowId = row.row_id ? String(row.row_id) : "";
    const isExpanded = rowId ? expandedRows.has(rowId) : false;
    return (
      <span className={`tree-cell depth-${row.depth ?? 0}`}>
        {row.is_expandable ? (
          <button
            className="tree-toggle"
            type="button"
            aria-label={isExpanded ? "Contraer fila" : "Expandir fila"}
            onClick={() => toggleRow(rowId)}
          >
            {isExpanded ? <ChevronDown size={14} /> : <ArrowRight size={14} />}
          </button>
        ) : (
          <span className="tree-spacer" />
        )}
        {value ?? "-"}
      </span>
    );
  }
  if (column.key.endsWith("_delta_percent")) {
    const metric = column.key.replace("_delta_percent", "");
    return (
      <MetricDelta
        value={typeof value === "number" ? value : null}
        state={
          row[`${metric}_semantic_state` as keyof DetailTableRow] as
            | string
            | null
        }
      />
    );
  }
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") {
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return value;
}

function MetricDelta({
  value,
  state,
}: {
  value: number | null;
  state?: string | null;
}) {
  if (value == null) return "-";
  return (
    <span className={`metric-delta semantic-${state ?? "neutral"}`}>
      {value >= 0 ? "+" : ""}
      {value.toLocaleString(undefined, { maximumFractionDigits: 2 })}%
    </span>
  );
}
