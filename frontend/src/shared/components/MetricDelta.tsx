type Props = {
  value?: number | null;
  formatted?: string | null;
  label?: string | null;
  precision?: number;
  intent?: "good" | "bad" | "positive" | "negative" | "neutral" | null;
};

export function MetricDelta({
  value,
  formatted,
  label,
  precision = 2,
  intent,
}: Props) {
  if (value === null || value === undefined) return null;
  const normalizedIntent =
    intent === "positive"
      ? "good"
      : intent === "negative"
        ? "bad"
        : (intent ?? "neutral");
  const rendered =
    formatted ?? `${value >= 0 ? "+" : ""}${value.toFixed(precision)}%`;
  return (
    <span className="metric-comparison">
      <strong
        className={`metric-delta metric-delta-${normalizedIntent}`}
        aria-label={`${label ?? "Delta"} ${rendered}`}
      >
        {rendered}
      </strong>
      {label ? <small>{label}</small> : null}
    </span>
  );
}
