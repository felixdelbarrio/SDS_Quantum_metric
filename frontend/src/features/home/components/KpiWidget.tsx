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

  return (
    <article
      className="dashboard-card kpi-card interactive-card"
      onDoubleClick={() => setExpanded(true)}
    >
      <div className="kpi-header">
        <span>{widget.title}</span>
        <MetricDelta
          value={widget.comparison?.delta_percent}
          intent={widget.semantic_intent}
        />
      </div>
      <strong className="kpi-value">
        {hasValue ? (
          <SemanticValue intent={widget.semantic_intent}>
            {formatValue(widget.value ?? 0, widget.unit)}
          </SemanticValue>
        ) : (
          "-"
        )}
      </strong>
      {hasValue ? (
        <>
          <QuantumChart payload={widget.chart_payload} title={widget.title} />
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

function formatValue(value: number, unit: KpiWidgetType["unit"]) {
  if (unit === "seconds") {
    return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })} s`;
  }
  if (unit === "percent") {
    return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}%`;
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}
