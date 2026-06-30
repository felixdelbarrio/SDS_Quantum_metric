import { QuantumChart } from "./QuantumChart";
import { QuantumChartProps } from "./chartTypes";

export function QuantumBarChart(props: QuantumChartProps) {
  return <QuantumChart {...props} displayMode="bar" />;
}
