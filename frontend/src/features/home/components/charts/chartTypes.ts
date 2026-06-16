import { ChartPayload } from "../../types";

export type QuantumChartMode = "compact" | "expanded";

export type QuantumChartProps = {
  payload?: ChartPayload | null;
  mode?: QuantumChartMode;
  title?: string;
};
