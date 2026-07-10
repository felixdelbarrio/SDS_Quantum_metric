import { ChartAxisTick } from "../../types";

const MAX_X_TICKS = 5;
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
              <text y="18">{String(tick.label || tick.value)}</text>
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
              {String(tick.label || tick.value)}
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
