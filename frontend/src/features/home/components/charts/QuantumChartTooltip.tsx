type Props = {
  label?: string;
};

export function QuantumChartTooltip({ label }: Props) {
  if (!label) return null;
  return <span className="sr-only">{label}</span>;
}
