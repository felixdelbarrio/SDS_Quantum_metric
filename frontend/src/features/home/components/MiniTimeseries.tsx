import { TimeseriesPoint } from "../types";

type Props = {
  points: TimeseriesPoint[];
};

export function MiniTimeseries({ points }: Props) {
  if (points.length < 2) {
    return <span className="mini-timeseries empty-line" aria-hidden="true" />;
  }

  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const width = 120;
  const height = 36;
  const d = points
    .map((point, index) => {
      const x = (index / (points.length - 1)) * width;
      const y = height - ((point.value - min) / range) * height;
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
      <path d={d} />
    </svg>
  );
}
