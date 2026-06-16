type Props = {
  label: string;
  value: string | number;
};

export function MetricBadge({ label, value }: Props) {
  return (
    <span className="metric-badge">
      <span>{label}</span>
      <strong>{value}</strong>
    </span>
  );
}
