import { ChartAxisTick } from "../../types";

const MAX_X_TICKS = 5;
const MEXICO_TIMEZONE = "America/Mexico_City";

type Props = {
  ticks: ChartAxisTick[];
  orientation: "x" | "y";
  width: number;
  height: number;
  padding: { top: number; right: number; bottom: number; left: number };
};

export function QuantumChartAxis({
  ticks,
  orientation,
  width,
  height,
  padding,
}: Props) {
  if (!ticks.length) return null;
  if (orientation === "x") {
    const y = height - padding.bottom;
    const visibleTicks = sampleTicks(ticks, MAX_X_TICKS);
    return (
      <g className="quantum-chart-axis quantum-chart-axis-x">
        <line x1={padding.left} y1={y} x2={width - padding.right} y2={y} />
        {visibleTicks.map(({ tick, originalIndex }) => {
          const x =
            padding.left +
            (tick.position ?? originalIndex / Math.max(1, ticks.length - 1)) *
              (width - padding.left - padding.right);
          return (
            <g
              key={`${tick.label}-${originalIndex}`}
              transform={`translate(${x} ${y})`}
            >
              <line y2="4" />
              <text y="18">{formatAxisLabel(tick.label || tick.value)}</text>
            </g>
          );
        })}
      </g>
    );
  }

  return (
    <g className="quantum-chart-axis quantum-chart-axis-y">
      {ticks.map((tick, index) => {
        const y =
          padding.top +
          (1 - (tick.position ?? index / Math.max(1, ticks.length - 1))) *
            (height - padding.top - padding.bottom);
        return (
          <g key={`${tick.label}-${index}`}>
            <line
              className="quantum-chart-grid"
              x1={padding.left}
              y1={y}
              x2={width - padding.right}
              y2={y}
            />
            <text x={padding.left - 8} y={y + 4}>
              {formatAxisLabel(tick.label || tick.value)}
            </text>
          </g>
        );
      })}
    </g>
  );
}

function sampleTicks(ticks: ChartAxisTick[], maxTicks: number) {
  if (ticks.length <= maxTicks) {
    return ticks.map((tick, originalIndex) => ({ tick, originalIndex }));
  }
  const step = (ticks.length - 1) / (maxTicks - 1);
  const indexes = Array.from({ length: maxTicks }, (_, index) =>
    Math.round(index * step),
  );
  return Array.from(new Set(indexes)).map((originalIndex) => ({
    tick: ticks[originalIndex],
    originalIndex,
  }));
}

function formatAxisLabel(value: number | string) {
  const text = String(value).trim();
  const numeric = Number(text);
  if (text && Number.isFinite(numeric) && Math.abs(numeric) > 1_000_000) {
    const millis =
      Math.abs(numeric) > 10_000_000_000 ? numeric : numeric * 1000;
    return new Intl.DateTimeFormat("en-US", {
      timeZone: MEXICO_TIMEZONE,
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(millis));
  }
  if (text.length > 14) return `${text.slice(0, 12)}...`;
  return text;
}
