import { Download, X } from "lucide-react";
import { useMemo, useState } from "react";
import { ErrorComparisonWidget, KpiWidget } from "../types";
import { QuantumChart } from "./charts/QuantumChart";

type Props = {
  widget: KpiWidget | ErrorComparisonWidget;
  open: boolean;
  onClose: () => void;
};

export function CardExplorerModal({ widget, open, onClose }: Props) {
  const [view, setView] = useState<"line" | "bar" | "table">("line");
  const rows = useMemo(() => pointsFromWidget(widget), [widget]);
  if (!open) return null;

  function exportCsv() {
    const header = ["series", "ts", "label", "value"];
    const body = rows.map((row) =>
      header.map((key) => csvCell(row[key as keyof typeof row])).join(","),
    );
    const blob = new Blob([[header.join(","), ...body].join("\n")], {
      type: "text/csv;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${widget.id}-points.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="card-explorer-modal" role="dialog" aria-modal="true">
        <header className="modal-header">
          <div>
            <span className="eyebrow">Card local</span>
            <h2>{widget.title}</h2>
          </div>
          <button
            className="icon-button"
            type="button"
            aria-label="Cerrar"
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </header>

        <div className="modal-toolbar">
          <div
            className="dashboard-tabs"
            role="tablist"
            aria-label="Vista de card"
          >
            {(["line", "bar", "table"] as const).map((option) => (
              <button
                key={option}
                className={view === option ? "active" : ""}
                type="button"
                role="tab"
                onClick={() => setView(option)}
              >
                {option === "line"
                  ? "Linea"
                  : option === "bar"
                    ? "Barras"
                    : "Tabla"}
              </button>
            ))}
          </div>
          <button className="command-button" type="button" onClick={exportCsv}>
            <Download size={16} /> CSV
          </button>
        </div>

        {view === "table" ? (
          <div className="table-scroll">
            <table className="table dashboard-table">
              <thead>
                <tr>
                  <th>Serie</th>
                  <th>Fecha</th>
                  <th>Label</th>
                  <th>Valor</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={`${row.series}-${row.ts}-${index}`}>
                    <td>{row.series}</td>
                    <td>{row.ts ?? "-"}</td>
                    <td>{row.label ?? "-"}</td>
                    <td>{formatNumber(row.value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <QuantumChart
            payload={widget.chart_payload}
            mode="expanded"
            displayMode={view}
            title={widget.title}
          />
        )}

        <p className="video-notice">
          La reproduccion de sesiones solo esta disponible en Quantum Web.
        </p>
      </section>
    </div>
  );
}

function pointsFromWidget(widget: KpiWidget | ErrorComparisonWidget) {
  const payload = widget.chart_payload;
  if (!payload) return [];
  return payload.series.flatMap((series) =>
    series.points.map((point) => ({
      series: series.label,
      ts: point.ts ?? null,
      label: point.label ?? null,
      value: point.value ?? null,
    })),
  );
}

function csvCell(value: string | number | null | undefined) {
  if (value === null || value === undefined) return "";
  return `"${String(value).replaceAll('"', '""')}"`;
}

function formatNumber(value?: number | null) {
  return value == null
    ? "-"
    : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}
