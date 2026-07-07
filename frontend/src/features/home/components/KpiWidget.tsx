import { Maximize2 } from "lucide-react";
import { useState } from "react";
import { MetricDelta } from "../../../shared/components/MetricDelta";
import { SemanticValue } from "../../../shared/components/SemanticValue";
import { KpiWidget as KpiWidgetType } from "../types";
import { CardExplorerModal } from "./CardExplorerModal";
import { QuantumChart } from "./charts/QuantumChart";

type Props = {
  widget: KpiWidgetType;
};

export function KpiWidget({ widget }: Props) {
  const [expanded, setExpanded] = useState(false);
  const hasValue = widget.value !== null && widget.value !== undefined;
  const isTable = widget.chart_type === "table";
  const tableRows = widget.table_rows ?? [];
  const tableColumns = widget.table_columns?.length
    ? widget.table_columns
    : inferColumns(tableRows);

  return (
    <article
      className="dashboard-card kpi-card interactive-card"
      onDoubleClick={() => setExpanded(true)}
    >
      <div className="kpi-header">
        <div>
          <span className="eyebrow">{domainLabel(widget)}</span>
          <h2>{widget.title}</h2>
        </div>
        <MetricDelta
          value={widget.comparison?.delta_percent}
          intent={widget.semantic_intent}
        />
      </div>
      <div className="kpi-value-row">
        <strong className="kpi-value">
          {hasValue ? (
            <SemanticValue intent={widget.semantic_intent}>
              {formatValue(widget.value ?? 0, widget.unit)}
            </SemanticValue>
          ) : (
            "-"
          )}
        </strong>
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
      {isTable ? (
        <GenericTablePreview columns={tableColumns} rows={tableRows} />
      ) : hasValue ? (
        <>
          {widget.breakdown.length ? (
            <div className="kpi-segment-values">
              {widget.breakdown.slice(0, 2).map((item) => (
                <span key={item.label}>
                  <small>{item.label}</small>
                  <strong>{formatValue(item.value, widget.unit)}</strong>
                </span>
              ))}
            </div>
          ) : null}
          {widget.chart_payload || !widget.role?.startsWith("generic.") ? (
            <QuantumChart payload={widget.chart_payload} title={widget.title} />
          ) : null}
          <div className="breakdown-list">
            {widget.breakdown.slice(0, 3).map((item) => (
              <span key={item.label}>
                {item.label}: {formatValue(item.value, widget.unit)}
              </span>
            ))}
          </div>
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
  columns: string[];
  rows: Array<Record<string, unknown>>;
}) {
  if (!rows.length || !columns.length) {
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
              <th key={column}>{labelForColumn(column)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 5).map((row, index) => (
            <tr key={String(row.row_index ?? index)}>
              {columns.slice(0, 4).map((column) => (
                <td key={column}>{formatCell(row[column])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function inferColumns(rows: Array<Record<string, unknown>>) {
  if (!rows.length) return [];
  return Object.keys(rows[0]).filter((key) => key !== "row_index");
}

function labelForColumn(value: string) {
  return value
    .replace(/^dimension_/, "Dimension ")
    .replace(/^metric_/, "Metric ")
    .replaceAll("_", " ");
}

function formatCell(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") {
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(value);
}

function domainLabel(widget: KpiWidgetType) {
  return widget.role?.startsWith("errors.") || widget.id.includes("error")
    ? "Errores"
    : "Resumen";
}

function formatValue(value: number, unit: KpiWidgetType["unit"]) {
  if (unit === "seconds") {
    return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })} s`;
  }
  if (unit === "percent") {
    return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}%`;
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}
