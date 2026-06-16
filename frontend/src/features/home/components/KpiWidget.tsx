import { KpiWidget as KpiWidgetType } from "../types";
import { MiniTimeseries } from "./MiniTimeseries";

type Props = {
  widget: KpiWidgetType;
};

export function KpiWidget({ widget }: Props) {
  const hasValue = widget.value !== null && widget.value !== undefined;

  return (
    <article className="dashboard-card kpi-card">
      <div className="kpi-header">
        <span>{widget.title}</span>
        {widget.comparison?.delta_percent !== null &&
          widget.comparison?.delta_percent !== undefined && (
            <strong
              className={
                widget.comparison.delta_percent >= 0 ? "delta up" : "delta down"
              }
            >
              {widget.comparison.delta_percent >= 0 ? "+" : ""}
              {widget.comparison.delta_percent.toFixed(2)}%
            </strong>
          )}
      </div>
      <strong className="kpi-value">
        {hasValue ? formatValue(widget.value ?? 0, widget.unit) : "-"}
      </strong>
      {hasValue ? (
        <>
          <MiniTimeseries points={widget.timeseries} />
          {widget.period?.label && (
            <span className="chart-date">{widget.period.label}</span>
          )}
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
