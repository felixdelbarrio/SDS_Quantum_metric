import { Maximize2 } from "lucide-react";
import { useState } from "react";
import { MetricDelta } from "../../../shared/components/MetricDelta";
import { SemanticValue } from "../../../shared/components/SemanticValue";
import type {
  DisplayNumberContract,
  KpiBreakdownItem,
  KpiWidget as KpiWidgetType,
} from "../types";
import { CardExplorerModal } from "./CardExplorerModal";
import { QuantumFormattedValue } from "./QuantumFormattedValue";
import { QuantumChart } from "./charts/QuantumChart";

type Props = {
  widget: KpiWidgetType;
};

export function KpiWidget({ widget }: Props) {
  const [expanded, setExpanded] = useState(false);
  const segments = widget.breakdown.filter(
    (item): item is KpiBreakdownItem & { display: DisplayNumberContract } =>
      Boolean(item.display),
  );
  const hasValue = Boolean(widget.display || segments.length);
  const tableRows = widget.table?.rows ?? [];
  const tableColumns = widget.table?.columns ?? [];
  const semanticIntent = comparisonIntent(widget);

  return (
    <article
      className={`dashboard-card kpi-card interactive-card ${widget.table ? "table-card" : widget.chart ? "chart-card" : "compact-kpi"}`}
      onDoubleClick={() => setExpanded(true)}
    >
      <div className="kpi-header">
        <div>
          <span className="eyebrow">Quantum</span>
          <h2>{widget.title}</h2>
        </div>
        <MetricDelta
          value={widget.comparison?.display_delta}
          formatted={widget.comparison?.formatted}
          label={widget.comparison?.label}
          precision={widget.comparison?.precision}
          intent={widget.comparison?.semantic_intent}
        />
      </div>
      <div
        className={`kpi-value-row ${widget.table ? "table-widget-actions" : ""}`}
      >
        {widget.table ? null : segments.length ? (
          <div className="kpi-segment-values">
            {segments.map((item) => (
              <span key={item.label}>
                <small>{item.label}</small>
                <strong>
                  <QuantumFormattedValue display={item.display} />
                </strong>
              </span>
            ))}
          </div>
        ) : (
          <strong className="kpi-value">
            {widget.display ? (
              <SemanticValue intent={semanticIntent}>
                <QuantumFormattedValue display={widget.display} />
              </SemanticValue>
            ) : (
              "-"
            )}
          </strong>
        )}
        <button
          className="icon-button subtle"
          type="button"
          aria-label={`Abrir detalle de ${widget.title}`}
          title="Abrir detalle"
          onClick={() => setExpanded(true)}
        >
          <Maximize2 size={16} />
        </button>
      </div>
      {widget.table ? (
        <GenericTablePreview columns={tableColumns} rows={tableRows} />
      ) : hasValue || widget.chart ? (
        <>
          {widget.chart ? (
            <QuantumChart payload={widget.chart} title={widget.title} />
          ) : null}
        </>
      ) : (
        <span className="widget-missing">
          Falta campo fuente: {widget.missing_source_field ?? widget.id}
        </span>
      )}
      <button
        className="card-open-button"
        type="button"
        onClick={() => setExpanded(true)}
      >
        Abrir detalle
      </button>
      <CardExplorerModal
        widget={widget}
        open={expanded}
        onClose={() => setExpanded(false)}
      />
    </article>
  );
}

function GenericTablePreview({
  columns,
  rows,
}: {
  columns: NonNullable<KpiWidgetType["table"]>["columns"];
  rows: Array<Record<string, unknown>>;
}) {
  if (!columns.length) {
    return (
      <span className="widget-missing">Sin filas locales para esta tabla</span>
    );
  }
  return (
    <div className="generic-widget-table">
      <table className="table dashboard-table">
        <thead>
          <tr>
            {columns.slice(0, 4).map((column) => (
              <th key={column.key}>{column.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length ? (
            rows.slice(0, 5).map((row, index) => (
              <tr key={String(row.row_index ?? index)}>
                {columns.slice(0, 4).map((column) => (
                  <td key={column.key}>{formatCell(row, column)}</td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td
                className="table-empty-cell"
                colSpan={Math.min(4, columns.length)}
              >
                Sin datos
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function formatCell(
  row: Record<string, unknown>,
  column: NonNullable<KpiWidgetType["table"]>["columns"][number],
) {
  const formatted = row[`${column.key}_formatted`];
  const value = row[column.key];
  const rendered =
    typeof formatted === "string" && formatted
      ? formatted
      : formatRawCell(value, column);
  const delta = row[`${column.key}_delta_formatted`];
  if (typeof delta !== "string" || !delta) return rendered;
  const intent = row[`${column.key}_delta_intent`];
  return (
    <span
      className={`table-metric-with-delta table-delta-${String(intent ?? "neutral")}`}
    >
      <span>{rendered}</span>
      <small>{delta}</small>
    </span>
  );
}

function formatRawCell(
  value: unknown,
  column: NonNullable<KpiWidgetType["table"]>["columns"][number],
) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") {
    const precision = column.precision ?? 0;
    const rendered = value.toLocaleString("en-US", {
      minimumFractionDigits: precision,
      maximumFractionDigits: precision,
    });
    return column.data_type === "percent" ? `${rendered}%` : rendered;
  }
  return String(value);
}

function comparisonIntent(widget: KpiWidgetType) {
  const intent = widget.comparison?.semantic_intent;
  if (intent === "positive") return "good";
  if (intent === "negative") return "bad";
  return "neutral";
}
