import {
  ChartAxis,
  ChartAxisTick,
  ChartBand,
  ChartSeriesPoint,
} from "../../types";

type Props = {
  bands: ChartBand[];
  chartType: "line" | "bar" | "area" | "stacked_bar" | "donut" | "mixed";
  ticks: ChartAxisTick[];
  yAxis: ChartAxis;
  width: number;
  height: number;
  padding: { top: number; right: number; bottom: number; left: number };
};

export function QuantumChartBands({
  bands,
  chartType,
  ticks,
  yAxis,
  width,
  height,
  padding,
}: Props) {
  if (!bands.length) return null;
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  return (
    <g className="quantum-chart-bands">
      {bands.map((band, index) => {
        const whiskers = historicalWhiskers(
          band,
          chartType,
          yAxis,
          width,
          height,
          padding,
        );
        if (whiskers) {
          return (
            <g
              key={band.band_id ?? band.id ?? `band-${index}`}
              className="quantum-chart-whiskers"
            >
              {whiskers.map((whisker, whiskerIndex) => (
                <g key={whiskerIndex}>
                  <line
                    x1={whisker.x}
                    x2={whisker.x}
                    y1={whisker.low}
                    y2={whisker.high}
                  />
                  <line
                    x1={whisker.x - 5}
                    x2={whisker.x + 5}
                    y1={whisker.low}
                    y2={whisker.low}
                  />
                  <line
                    x1={whisker.x - 5}
                    x2={whisker.x + 5}
                    y1={whisker.high}
                    y2={whisker.high}
                  />
                </g>
              ))}
            </g>
          );
        }
        const areaPath = historicalAreaPath(
          band,
          yAxis,
          width,
          height,
          padding,
        );
        if (areaPath) {
          return (
            <path
              key={band.band_id ?? band.id ?? `band-${index}`}
              className={`quantum-chart-band quantum-chart-band-${band.kind ?? "custom"}`}
              d={areaPath}
            />
          );
        }
        const start =
          band.start_x ?? exactTickPosition(ticks, band.start ?? band.start_ts);
        const end =
          band.end_x ?? exactTickPosition(ticks, band.end ?? band.end_ts);
        if (start === undefined || end === undefined) return null;
        return (
          <rect
            key={band.band_id ?? band.id ?? `band-${index}`}
            className={`quantum-chart-band quantum-chart-band-${band.kind ?? "custom"} quantum-chart-band-pattern-${band.pattern ?? "solid"}`}
            x={padding.left + start * plotWidth}
            y={padding.top}
            width={Math.max(1, (end - start) * plotWidth)}
            height={plotHeight}
          />
        );
      })}
    </g>
  );
}

function historicalWhiskers(
  band: ChartBand,
  chartType: Props["chartType"],
  yAxis: ChartAxis,
  width: number,
  height: number,
  padding: Props["padding"],
) {
  if (chartType !== "bar" && chartType !== "stacked_bar") return null;
  const lower = band.lower_points ?? [];
  const upper = band.upper_points ?? [];
  if (!lower.length || lower.length !== upper.length) return null;
  const values = [...lower, ...upper]
    .map(pointValue)
    .filter((value): value is number => value !== null);
  if (!values.length) return null;
  const min = yAxis.min ?? Math.min(...values);
  const max = yAxis.max ?? Math.max(...values);
  const range = max - min || 1;
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const renderY = (value: number) =>
    padding.top + (1 - (value - min) / range) * plotHeight;
  return lower.flatMap((point, index) => {
    const low = pointValue(point);
    const high = pointValue(upper[index]);
    if (low === null || high === null) return [];
    const x =
      padding.left +
      (point.x ?? index / Math.max(1, lower.length - 1)) * plotWidth;
    return [{ x, low: renderY(low), high: renderY(high) }];
  });
}

function historicalAreaPath(
  band: ChartBand,
  yAxis: ChartAxis,
  width: number,
  height: number,
  padding: Props["padding"],
) {
  const lower = band.lower_points ?? [];
  const upper = band.upper_points ?? [];
  if (!lower.length || lower.length !== upper.length) return null;
  const values = [...lower, ...upper]
    .map(pointValue)
    .filter((value): value is number => value !== null);
  if (!values.length) return null;
  const min = yAxis.min ?? Math.min(...values);
  const max = yAxis.max ?? Math.max(...values);
  const range = max - min || 1;
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const render = (point: ChartSeriesPoint, index: number, count: number) => {
    const value = pointValue(point) ?? min;
    const x =
      padding.left + (point.x ?? index / Math.max(1, count - 1)) * plotWidth;
    const y = padding.top + (1 - (value - min) / range) * plotHeight;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  };
  const upperPath = upper.map((point, index) =>
    render(point, index, upper.length),
  );
  const lowerPath = [...lower]
    .reverse()
    .map((point, index) =>
      render(point, lower.length - index - 1, lower.length),
    );
  return `M${upperPath.join(" L")} L${lowerPath.join(" L")} Z`;
}

function pointValue(point: ChartSeriesPoint) {
  return typeof point.value === "number"
    ? point.value
    : typeof point.raw_value === "number"
      ? point.raw_value
      : null;
}

function exactTickPosition(ticks: ChartAxisTick[], value?: string | null) {
  if (!value) return undefined;
  const index = ticks.findIndex((tick) => String(tick.value) === value);
  if (index < 0) return undefined;
  return ticks[index].position ?? index / Math.max(1, ticks.length - 1);
}
