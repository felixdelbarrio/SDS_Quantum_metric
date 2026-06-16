import { useState } from "react";
import { ErrorComparisonWidget } from "../types";
import { CardExplorerModal } from "./CardExplorerModal";
import { QuantumChart } from "./charts/QuantumChart";

type Props = {
  widget: ErrorComparisonWidget;
};

export function ErrorDonut({ widget }: Props) {
  const [expanded, setExpanded] = useState(false);
  const total = widget.series.reduce((sum, point) => sum + point.value, 0);

  return (
    <article
      className="dashboard-card error-donut-card interactive-card"
      onDoubleClick={() => setExpanded(true)}
    >
      <div className="section-heading">
        <div>
          <h2>{widget.title}</h2>
          <span>Total: {widget.total?.toLocaleString() ?? "-"}</span>
        </div>
      </div>

      {total > 0 ? (
        <QuantumChart payload={widget.chart_payload} title={widget.title} />
      ) : (
        <div className="analytics-empty compact">
          Sin sesiones con error calculables
        </div>
      )}
      {widget.period?.label && (
        <span className="chart-date">{widget.period.label}</span>
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
