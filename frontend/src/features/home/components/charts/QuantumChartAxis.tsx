import { ChartAxisTick } from "../../types";

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
    return (
      <g className="quantum-chart-axis quantum-chart-axis-x">
        <line x1={padding.left} y1={y} x2={width - padding.right} y2={y} />
        {ticks.map((tick, index) => {
          const x =
            padding.left +
            (tick.position ?? index / Math.max(1, ticks.length - 1)) *
              (width - padding.left - padding.right);
          return (
            <g
              key={`${tick.label}-${index}`}
              transform={`translate(${x} ${y})`}
            >
              <line y2="4" />
              <text y="18">{tick.label}</text>
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
              {tick.label}
            </text>
          </g>
        );
      })}
    </g>
  );
}
