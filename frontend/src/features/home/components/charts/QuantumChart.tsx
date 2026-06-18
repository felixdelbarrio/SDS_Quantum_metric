import { Download } from "lucide-react";
import { useMemo, useRef, useState } from "react";
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
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [activePoint, setActivePoint] = useState<RenderedPoint | null>(null);
  const size = mode === "expanded" ? EXPANDED_SIZE : COMPACT_SIZE;
  const renderModel = useMemo(
    () =>
      payload && payload.chart_type !== "donut"
        ? buildLineRenderModel(payload, size)
        : { paths: [], points: [] },
    [payload, size],
  );

  if (!payload) {
    return (
      <div className="quantum-chart-empty contract-failure" role="alert">
        <strong>Fallo contractual de grafica local</strong>
        <span>
          Regenera derivados, ejecuta regresion o lanza una nueva ingesta.
        </span>
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
        ref={svgRef}
        viewBox={`0 0 ${size.width} ${size.height}`}
        role="img"
        aria-label={ariaLabel}
        onMouseLeave={() => setActivePoint(null)}
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
        {renderModel.paths.map((path, index) => (
          <path
            key={path.id}
            className={`quantum-chart-series quantum-chart-series-${index % 5}`}
            d={path.d}
          />
        ))}
        <g className="quantum-chart-points">
          {renderModel.points.map((point) => (
            <circle
              key={`${point.seriesId}-${point.index}`}
              className={`quantum-chart-point quantum-chart-series-${point.seriesIndex % 5}`}
              cx={point.x}
              cy={point.y}
              r="4"
              tabIndex={0}
              role="button"
              aria-label={`${point.seriesLabel} ${point.label}: ${formatNumber(point.value)}`}
              onMouseEnter={() => setActivePoint(point)}
              onFocus={() => setActivePoint(point)}
              onBlur={() => setActivePoint(null)}
            />
          ))}
        </g>
      </svg>
      {activePoint ? <ChartTooltip point={activePoint} /> : null}
      <QuantumChartLegend payload={payload} />
      <div className="chart-actions" aria-label="Descargas de grafica">
        <button
          className="icon-text-button"
          type="button"
          onClick={() => downloadCsv(payload, title)}
        >
          <Download size={14} /> CSV
        </button>
        <button
          className="icon-text-button"
          type="button"
          onClick={() => downloadSvg(svgRef.current, title)}
        >
          <Download size={14} /> SVG
        </button>
        <button
          className="icon-text-button"
          type="button"
          onClick={() => downloadPng(svgRef.current, title)}
        >
          <Download size={14} /> PNG
        </button>
      </div>
      {payload.period_label && <figcaption>{payload.period_label}</figcaption>}
      <QuantumChartTooltip label={ariaLabel} />
    </figure>
  );
}

type RenderedPoint = {
  seriesId: string;
  seriesLabel: string;
  seriesIndex: number;
  index: number;
  label: string;
  ts?: string | null;
  value?: number | null;
  x: number;
  y: number;
};

function buildLineRenderModel(
  payload: ChartPayload,
  size: typeof COMPACT_SIZE,
): { paths: Array<{ id: string; d: string }>; points: RenderedPoint[] } {
  const min = payload.y_axis.min ?? minValue(payload);
  const max = payload.y_axis.max ?? maxValue(payload);
  const range = max - min || 1;
  const plotWidth = size.width - size.padding.left - size.padding.right;
  const plotHeight = size.height - size.padding.top - size.padding.bottom;
  const paths: Array<{ id: string; d: string }> = [];
  const points: RenderedPoint[] = [];
  payload.series
    .filter((series) => series.visible !== false && series.points.length)
    .forEach((series, seriesIndex) => {
      const denominator = Math.max(1, series.points.length - 1);
      const commands: string[] = [];
      series.points.forEach((point, index) => {
        const x =
          size.padding.left + (point.x ?? index / denominator) * plotWidth;
        const y =
          size.padding.top +
          (1 - ((point.value ?? 0) - min) / range) * plotHeight;
        commands.push(
          `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`,
        );
        points.push({
          seriesId: series.id,
          seriesLabel: series.label,
          seriesIndex,
          index,
          label: point.label ?? point.ts ?? `Punto ${index + 1}`,
          ts: point.ts,
          value: point.value,
          x,
          y,
        });
      });
      paths.push({ id: series.id, d: commands.join(" ") });
    });
  return { paths, points };
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

function ChartTooltip({ point }: { point: RenderedPoint }) {
  return (
    <div className="quantum-chart-tooltip" role="status">
      <strong>{point.seriesLabel}</strong>
      <span>{point.label}</span>
      <span>{formatNumber(point.value)}</span>
    </div>
  );
}

function downloadCsv(payload: ChartPayload, title?: string) {
  const header = ["series", "ts", "label", "value"];
  const rows = payload.series.flatMap((series) =>
    series.points.map((point) => [
      series.label,
      point.ts ?? "",
      point.label ?? "",
      point.value ?? "",
    ]),
  );
  downloadBlob(
    [[header, ...rows].map((row) => row.map(csvCell).join(",")).join("\n")],
    `${fileSlug(title)}-chart.csv`,
    "text/csv;charset=utf-8",
  );
}

function downloadSvg(svg: SVGSVGElement | null, title?: string) {
  if (!svg) return;
  downloadBlob(
    [svg.outerHTML],
    `${fileSlug(title)}-chart.svg`,
    "image/svg+xml;charset=utf-8",
  );
}

function downloadPng(svg: SVGSVGElement | null, title?: string) {
  if (!svg) return;
  const image = new Image();
  const blob = new Blob([svg.outerHTML], {
    type: "image/svg+xml;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  image.onload = () => {
    const canvas = document.createElement("canvas");
    canvas.width = svg.viewBox.baseVal.width || svg.clientWidth;
    canvas.height = svg.viewBox.baseVal.height || svg.clientHeight;
    const context = canvas.getContext("2d");
    if (context) {
      context.drawImage(image, 0, 0);
      canvas.toBlob((pngBlob) => {
        if (pngBlob) {
          downloadBlob([pngBlob], `${fileSlug(title)}-chart.png`, "image/png");
        }
      });
    }
    URL.revokeObjectURL(url);
  };
  image.src = url;
}

function downloadBlob(parts: BlobPart[], filename: string, type: string) {
  const blob = new Blob(parts, { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function csvCell(value: string | number | null | undefined) {
  if (value === null || value === undefined) return "";
  return `"${String(value).replaceAll('"', '""')}"`;
}

function fileSlug(value?: string) {
  return (value ?? "quantum")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function formatNumber(value?: number | null) {
  return value == null
    ? "-"
    : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
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
