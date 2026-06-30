import { Download, FileDown, ImageDown } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { ChartPayload, ChartSeriesPoint } from "../../types";
import { QuantumChartAxis } from "./QuantumChartAxis";
import { QuantumChartBands } from "./QuantumChartBands";
import { QuantumChartLegend } from "./QuantumChartLegend";
import { QuantumChartTooltip } from "./QuantumChartTooltip";
import { QuantumChartProps } from "./chartTypes";

const MEXICO_TIMEZONE = "America/Mexico_City";

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
  displayMode,
  title,
}: QuantumChartProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [activePoint, setActivePoint] = useState<RenderedPoint | null>(null);
  const size = mode === "expanded" ? EXPANDED_SIZE : COMPACT_SIZE;
  const chartMode =
    displayMode ?? (payload?.chart_type === "bar" ? "bar" : "line");
  const renderModel = useMemo(
    () =>
      payload && payload.chart_type !== "donut"
        ? buildChartRenderModel(payload, size, chartMode)
        : { paths: [], bars: [], points: [] },
    [payload, size, chartMode],
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
    ? `${title}. Grafica ${chartMode}`
    : `Grafica ${chartMode}`;

  return (
    <figure
      className={`quantum-chart quantum-chart-${mode} quantum-chart-display-${chartMode}`}
    >
      <div className="quantum-chart-stage">
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
          {renderModel.bars.map((bar) => {
            const isActive =
              activePoint?.seriesId === bar.seriesId &&
              activePoint.index === bar.index;
            return (
              <rect
                key={`${bar.seriesId}-${bar.index}`}
                className={`quantum-chart-bar quantum-chart-series-${bar.seriesIndex % 5}`}
                data-active={isActive ? "true" : "false"}
                x={bar.barX}
                y={bar.barY}
                width={bar.barWidth}
                height={bar.barHeight}
                rx="1.5"
                tabIndex={0}
                role="button"
                aria-label={`${bar.seriesLabel} ${bar.label}: ${formatNumber(bar.value)}`}
                onMouseEnter={() => setActivePoint(bar)}
                onFocus={() => setActivePoint(bar)}
                onBlur={() => setActivePoint(null)}
              />
            );
          })}
          {renderModel.paths.map((path, index) => (
            <path
              key={path.id}
              className={`quantum-chart-series quantum-chart-series-${index % 5}`}
              d={path.d}
            />
          ))}
          {chartMode === "line" ? (
            <g className="quantum-chart-points">
              {renderModel.points.map((point) => {
                const isActive =
                  activePoint?.seriesId === point.seriesId &&
                  activePoint.index === point.index;
                return (
                  <circle
                    key={`${point.seriesId}-${point.index}`}
                    className={`quantum-chart-point quantum-chart-series-${point.seriesIndex % 5}`}
                    data-active={isActive ? "true" : "false"}
                    cx={point.x}
                    cy={point.y}
                    r="3"
                    tabIndex={0}
                    role="button"
                    aria-label={`${point.seriesLabel} ${point.label}: ${formatNumber(point.value)}`}
                    onMouseEnter={() => setActivePoint(point)}
                    onFocus={() => setActivePoint(point)}
                    onBlur={() => setActivePoint(null)}
                  />
                );
              })}
            </g>
          ) : null}
        </svg>
        {activePoint ? <ChartTooltip point={activePoint} /> : null}
      </div>
      <QuantumChartLegend payload={payload} />
      <div className="chart-actions" aria-label="Descargas de grafica">
        <button
          className="icon-text-button"
          type="button"
          title="Descargar CSV"
          aria-label="Descargar CSV"
          onClick={() => downloadCsv(payload, title)}
        >
          <FileDown size={14} /> CSV
        </button>
        <button
          className="icon-text-button"
          type="button"
          title="Descargar SVG"
          aria-label="Descargar SVG"
          onClick={() => downloadSvg(svgRef.current, title)}
        >
          <Download size={14} /> SVG
        </button>
        <button
          className="icon-text-button"
          type="button"
          title="Descargar PNG"
          aria-label="Descargar PNG"
          onClick={() => downloadPng(svgRef.current, title)}
        >
          <ImageDown size={14} /> PNG
        </button>
      </div>
      {payload.period_label && (
        <figcaption>{formatPeriodCaption(payload.period_label)}</figcaption>
      )}
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
  barX?: number;
  barY?: number;
  barWidth?: number;
  barHeight?: number;
};

function buildChartRenderModel(
  payload: ChartPayload,
  size: typeof COMPACT_SIZE,
  displayMode: "line" | "bar",
): {
  paths: Array<{ id: string; d: string }>;
  bars: RenderedPoint[];
  points: RenderedPoint[];
} {
  const min = payload.y_axis.min ?? minValue(payload);
  const max = payload.y_axis.max ?? maxValue(payload);
  const range = max - min || 1;
  const plotWidth = size.width - size.padding.left - size.padding.right;
  const plotHeight = size.height - size.padding.top - size.padding.bottom;
  const paths: Array<{ id: string; d: string }> = [];
  const bars: RenderedPoint[] = [];
  const points: RenderedPoint[] = [];
  const visibleSeries = payload.series.filter(
    (series) => series.visible !== false && series.points.length,
  );
  const maxPointCount = Math.max(
    1,
    ...visibleSeries.map((series) => series.points.length),
  );
  const valueToY = (value: number) =>
    size.padding.top + (1 - (value - min) / range) * plotHeight;
  const baseline =
    min < 0 && max > 0 ? valueToY(0) : size.padding.top + plotHeight;
  const groupWidth = Math.min(
    42,
    (plotWidth / Math.max(1, maxPointCount)) * 0.7,
  );
  const barWidth = Math.max(
    2,
    (groupWidth / Math.max(1, visibleSeries.length)) * 0.78,
  );
  visibleSeries.forEach((series, seriesIndex) => {
    const denominator = Math.max(1, series.points.length - 1);
    const seriesPoints: RenderedPoint[] = [];
    series.points.forEach((point, index) => {
      const x =
        size.padding.left + (point.x ?? index / denominator) * plotWidth;
      const value = point.value ?? 0;
      const y = valueToY(value);
      const barX =
        x -
        groupWidth / 2 +
        seriesIndex * (groupWidth / Math.max(1, visibleSeries.length)) +
        (groupWidth / Math.max(1, visibleSeries.length) - barWidth) / 2;
      const renderedPoint = {
        seriesId: series.id,
        seriesLabel: series.label,
        seriesIndex,
        index,
        label: formatPointLabel(
          point.label ?? point.ts ?? `Punto ${index + 1}`,
        ),
        ts: point.ts,
        value: point.value,
        x,
        y,
        barX,
        barY: Math.min(y, baseline),
        barWidth,
        barHeight: Math.max(1, Math.abs(baseline - y)),
      };
      seriesPoints.push(renderedPoint);
    });
    points.push(...seriesPoints);
    if (displayMode === "bar") {
      bars.push(...seriesPoints);
    } else {
      paths.push({ id: series.id, d: smoothPath(seriesPoints) });
    }
  });
  return { paths, bars, points };
}

function smoothPath(points: Array<Pick<RenderedPoint, "x" | "y">>) {
  if (!points.length) return "";
  const start = points[0];
  if (points.length === 1) {
    return `M ${formatCoord(start.x)} ${formatCoord(start.y)}`;
  }
  if (points.length === 2) {
    const end = points[1];
    return `M ${formatCoord(start.x)} ${formatCoord(start.y)} L ${formatCoord(end.x)} ${formatCoord(end.y)}`;
  }

  const commands = [`M ${formatCoord(start.x)} ${formatCoord(start.y)}`];
  for (let index = 0; index < points.length - 1; index += 1) {
    const previous = points[index - 1] ?? points[index];
    const current = points[index];
    const next = points[index + 1];
    const following = points[index + 2] ?? next;
    const controlOne = {
      x: current.x + (next.x - previous.x) / 6,
      y: current.y + (next.y - previous.y) / 6,
    };
    const controlTwo = {
      x: next.x - (following.x - current.x) / 6,
      y: next.y - (following.y - current.y) / 6,
    };
    commands.push(
      `C ${formatCoord(controlOne.x)} ${formatCoord(controlOne.y)} ${formatCoord(controlTwo.x)} ${formatCoord(controlTwo.y)} ${formatCoord(next.x)} ${formatCoord(next.y)}`,
    );
  }
  return commands.join(" ");
}

function formatCoord(value: number) {
  return value.toFixed(2);
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

function formatPercent(value?: number | null) {
  return value == null
    ? "-"
    : `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}%`;
}

function QuantumDonutChart({
  payload,
  mode,
  title,
}: QuantumChartProps & { payload: ChartPayload }) {
  const points = payload.series[0]?.points ?? [];
  const segments = donutSegments(points);
  let offset = 25;
  return (
    <figure
      className={`quantum-chart quantum-chart-donut quantum-chart-${mode}`}
    >
      <svg viewBox="0 0 42 42" role="img" aria-label={title ?? "Donut"}>
        <circle className="quantum-donut-track" cx="21" cy="21" r="15.915" />
        {segments.map((segment, index) => {
          const element = (
            <circle
              key={`${segment.label}-${index}`}
              className={`quantum-donut-segment quantum-donut-segment-${index % 5}`}
              cx="21"
              cy="21"
              r="15.915"
              strokeDasharray={`${segment.dash} ${100 - segment.dash}`}
              strokeDashoffset={offset}
            />
          );
          offset -= segment.dash;
          return element;
        })}
      </svg>
      <ul className="donut-breakdown" aria-label="Detalle de segmentos">
        {segments.map((segment, index) => (
          <li key={`${segment.label}-${index}`}>
            <span>
              <i className={`chart-swatch chart-swatch-${index % 5}`} />
              <strong>{segment.label}</strong>
            </span>
            <span>
              {formatNumber(segment.value)} - {formatPercent(segment.percent)}
            </span>
          </li>
        ))}
      </ul>
      {payload.period_label && (
        <figcaption>{formatPeriodCaption(payload.period_label)}</figcaption>
      )}
    </figure>
  );
}

function donutSegments(points: ChartSeriesPoint[]) {
  const values = points.map((point) => point.value ?? 0);
  const valueTotal = values.reduce((sum, value) => sum + value, 0);
  const rawSegments = points.map((point, index) => {
    const value = values[index] ?? 0;
    const rawPercent =
      typeof point.raw_value === "number" && point.raw_value > 0
        ? point.raw_value
        : valueTotal
          ? (value / valueTotal) * 100
          : 0;
    return {
      label: String(point.label ?? `Segmento ${index + 1}`),
      value,
      percent: rawPercent,
    };
  });
  const percentTotal = rawSegments.reduce(
    (sum, segment) => sum + segment.percent,
    0,
  );
  return rawSegments.map((segment) => ({
    ...segment,
    dash: percentTotal ? (segment.percent / percentTotal) * 100 : 0,
  }));
}

function formatPointLabel(value: string | number) {
  const date = dateFromEpochLike(value);
  if (!date) return String(value);
  return new Intl.DateTimeFormat("en-US", {
    timeZone: MEXICO_TIMEZONE,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function formatPeriodCaption(value: string) {
  const match = value.match(
    /(\d{10,13})\s*-\s*(\d{10,13})(?:\s+([A-Z]{2,4}))?/,
  );
  if (!match) return value;
  const start = dateFromEpochLike(match[1]);
  const end = dateFromEpochLike(match[2]);
  if (!start || !end) return value;
  const timezoneLabel = match[3] ?? "CST";
  const dateFormatter = new Intl.DateTimeFormat("en-US", {
    timeZone: MEXICO_TIMEZONE,
    month: "short",
    day: "2-digit",
    year: "numeric",
  });
  const timeFormatter = new Intl.DateTimeFormat("en-US", {
    timeZone: MEXICO_TIMEZONE,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const startDate = dateFormatter.format(start);
  const endDate = dateFormatter.format(end);
  const startTime = timeFormatter.format(start);
  const endTime = timeFormatter.format(end);
  if (startDate === endDate) {
    return `${startDate}, ${startTime} - ${endTime} ${timezoneLabel}`;
  }
  return `${startDate} ${startTime} - ${endDate} ${endTime} ${timezoneLabel}`;
}

function dateFromEpochLike(value: string | number) {
  const numeric = Number(String(value).trim());
  if (!Number.isFinite(numeric) || Math.abs(numeric) < 1_000_000) {
    return null;
  }
  const millis = Math.abs(numeric) > 10_000_000_000 ? numeric : numeric * 1000;
  const date = new Date(millis);
  return Number.isNaN(date.getTime()) ? null : date;
}
