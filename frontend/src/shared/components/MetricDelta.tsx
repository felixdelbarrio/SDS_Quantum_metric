type Props = {
  value?: number | null;
  intent?: "good" | "bad" | "neutral" | null;
};

export function MetricDelta({ value, intent }: Props) {
  if (value === null || value === undefined) return null;
  const normalizedIntent =
    intent ?? (value > 0 ? "good" : value < 0 ? "bad" : "neutral");
  return (
    <strong
      className={`metric-delta metric-delta-${normalizedIntent}`}
      aria-label={`Delta ${value.toFixed(2)} por ciento`}
    >
      {value >= 0 ? "+" : ""}
      {value.toFixed(2)}%
    </strong>
  );
}
