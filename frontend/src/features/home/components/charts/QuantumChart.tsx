import { useMemo } from "react";
import { ChartPayload, ChartSeriesPoint } from "../../types";
import { QuantumChartAxis } from "./QuantumChartAxis";
import { QuantumChartBands } from "./QuantumChartBands";
import { QuantumChartLegend } from "./QuantumChartLegend";
import { QuantumChartTooltip } from "./QuantumChartTooltip";
import { QuantumChartProps } from "./chartTypes";

const COMPACT_SIZE = {
  width: 320,
  height: 180,
  padding: { top: 14, right: 16, bottom: 38, left: 54 },
};

const EXPANDED_SIZE = {
  width: 760,
  height: 360,
  padding: { top: 24, right: 28, bottom: 52, left: 72 },
};

export function QuantumChart({
  payload,
  mode = "compact",
  title,
}: QuantumChartProps) {
  const size = mode === "expanded" ? EXPANDED_SIZE : COMPACT_SIZE;
  const paths = useMemo(
    () =>
      payload && payload.chart_type !== "donut"
        ? buildLinePaths(payload, size)
        : [],
    [payload, size],
  );

  if (!payload) {
    return (
      <div className="quantum-chart-empty contract-failure" role="alert">
        <strong>Fallo contractual de grafica local</strong>
        <span>La ultima ingesta no produjo un chart_payload valido.</span>
      </div>
    );
  }
  if (payload.chart_type === "donut") {
    return <QuantumDonutChart payload={payload} mode={mode} title={title} />;
  }

  const ariaLabel = title
    ? `${title}. Grafica ${payload.chart_type}`
    : `Grafica ${payload.chart_type}`;

  return (
    <figure className={`quantum-chart quantum-chart-${mode}`}>
      <svg
        viewBox={`0 0 ${size.width} ${size.height}`}
        role="img"
        aria-label={ariaLabel}
      >
        <QuantumChartBands
          bands={payload.bands}
          width={size.width}
          height={size.height}
          padding={size.padding}
        />
        <QuantumChartAxis
          ticks={payload.y_axis.ticks}
          orientation="y"
          width={size.width}
          height={size.height}
          padding={size.padding}
        />
        <QuantumChartAxis
          ticks={payload.x_axis.ticks}
          orientation="x"
          width={size.width}
          height={size.height}
          padding={size.padding}
        />
        {paths.map((path, index) => (
          <path
            key={path.id}
            className={`quantum-chart-series quantum-chart-series-${index % 5}`}
            d={path.d}
          />
        ))}
      </svg>
      <QuantumChartLegend payload={payload} />
      {payload.period_label && <figcaption>{payload.period_label}</figcaption>}
      <QuantumChartTooltip label={ariaLabel} />
    </figure>
  );
}

function buildLinePaths(
  payload: ChartPayload,
  size: typeof COMPACT_SIZE,
): Array<{ id: string; d: string }> {
  const min = payload.y_axis.min ?? minValue(payload);
  const max = payload.y_axis.max ?? maxValue(payload);
  const range = max - min || 1;
  const plotWidth = size.width - size.padding.left - size.padding.right;
  const plotHeight = size.height - size.padding.top - size.padding.bottom;
  return payload.series
    .filter((series) => series.visible !== false && series.points.length)
    .map((series) => {
      const denominator = Math.max(1, series.points.length - 1);
      const d = series.points
        .map((point, index) => {
          const x =
            size.padding.left + (point.x ?? index / denominator) * plotWidth;
          const y =
            size.padding.top +
            (1 - ((point.value ?? 0) - min) / range) * plotHeight;
          return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
        })
        .join(" ");
      return { id: series.id, d };
    });
}

function minValue(payload: ChartPayload) {
  const values = pointValues(payload);
  return values.length ? Math.min(...values, 0) : 0;
}

function maxValue(payload: ChartPayload) {
  const values = pointValues(payload);
  return values.length ? Math.max(...values, 1) : 1;
}

function pointValues(payload: ChartPayload) {
  return payload.series.flatMap((series) =>
    series.points
      .map((point: ChartSeriesPoint) => point.value)
      .filter((value): value is number => typeof value === "number"),
  );
}

function QuantumDonutChart({
  payload,
  mode,
  title,
}: QuantumChartProps & { payload: ChartPayload }) {
  const points = payload.series[0]?.points ?? [];
  const total = points.reduce((sum, point) => sum + (point.value ?? 0), 0);
  let offset = 25;
  return (
    <figure
      className={`quantum-chart quantum-chart-donut quantum-chart-${mode}`}
    >
      <svg viewBox="0 0 42 42" role="img" aria-label={title ?? "Donut"}>
        <circle className="quantum-donut-track" cx="21" cy="21" r="15.915" />
        {points.map((point, index) => {
          const dash = total ? ((point.value ?? 0) / total) * 100 : 0;
          const element = (
            <circle
              key={`${point.label ?? index}`}
              className={`quantum-donut-segment quantum-chart-series-${index % 5}`}
              cx="21"
              cy="21"
              r="15.915"
              strokeDasharray={`${dash} ${100 - dash}`}
              strokeDashoffset={offset}
            />
          );
          offset -= dash;
          return element;
        })}
      </svg>
      <QuantumChartLegend payload={payload} />
      {payload.period_label && <figcaption>{payload.period_label}</figcaption>}
    </figure>
  );
}
