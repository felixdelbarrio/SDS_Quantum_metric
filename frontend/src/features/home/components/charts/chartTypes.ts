import { ChartPayload } from "../../types";

export type QuantumChartMode = "compact" | "expanded";

export type QuantumChartProps = {
  payload?: ChartPayload | null;
  mode?: QuantumChartMode;
  displayMode?: "line" | "bar";
  title?: string;
};
