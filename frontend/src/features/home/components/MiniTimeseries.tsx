import { TimeseriesPoint } from "../types";

type Props = {
  points: TimeseriesPoint[];
};

export function MiniTimeseries({ points }: Props) {
  if (points.length < 2) {
    return (
      <svg
        className="mini-timeseries"
        viewBox="0 0 180 82"
        role="img"
        aria-label="Serie temporal sin suficientes puntos"
      >
        <line x1="8" y1="70" x2="172" y2="70" />
        <line x1="8" y1="42" x2="172" y2="42" />
        <line x1="8" y1="14" x2="172" y2="14" />
      </svg>
    );
  }

  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const width = 180;
  const height = 82;
  const padding = 8;
  const chartHeight = height - 20;
  const d = points
    .map((point, index) => {
      const x = padding + (index / (points.length - 1)) * (width - padding * 2);
      const y =
        padding + chartHeight - ((point.value - min) / range) * chartHeight;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg
      className="mini-timeseries"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Mini serie temporal"
    >
      <line x1="8" y1="70" x2="172" y2="70" />
      <line x1="8" y1="42" x2="172" y2="42" />
      <line x1="8" y1="14" x2="172" y2="14" />
      <path d={d} />
    </svg>
  );
}
