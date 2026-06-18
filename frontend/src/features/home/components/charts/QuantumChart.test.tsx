import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { QuantumChart } from "./QuantumChart";
import { ChartPayload } from "../../types";

describe("QuantumChart", () => {
  it("muestra fallo contractual cuando no existe chart payload local", () => {
    render(<QuantumChart payload={null} title="Paginas vistas" />);

    expect(
      screen.getByText("Fallo contractual de grafica local"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Sin contrato grafico local"),
    ).not.toBeInTheDocument();
  });

  it("pinta la fecha persistida debajo de la grafica", () => {
    render(<QuantumChart payload={chartPayload()} title="Paginas vistas" />);

    expect(screen.getByText("Jun 16, 2026 (CST)")).toBeInTheDocument();
  });

  it("normaliza etiquetas antiguas con epoch antes de mostrarlas", () => {
    render(<QuantumChart payload={rawEpochPayload()} title="Paginas vistas" />);

    expect(
      screen.getByText("Jun 17, 2026, 00:00 - 02:58 CST"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/1781676000/)).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Mobile 02:50: 180" }),
    ).toBeInTheDocument();
  });
});

function chartPayload(): ChartPayload {
  return {
    chart_type: "line",
    x_axis: {
      ticks: [
        { value: "2026-06-16T00:00:00Z", label: "00:00", position: 0 },
        { value: "2026-06-16T01:00:00Z", label: "01:00", position: 1 },
      ],
    },
    y_axis: {
      min: 0,
      max: 100,
      unit: "count",
      ticks: [
        { value: 0, label: "0", position: 0 },
        { value: 100, label: "100", position: 1 },
      ],
    },
    series: [
      {
        id: "mobile",
        label: "Mobile",
        kind: "line",
        device: "mobile",
        visible: true,
        points: [
          { ts: "2026-06-16T00:00:00Z", label: "00:00", value: 10 },
          { ts: "2026-06-16T01:00:00Z", label: "01:00", value: 20 },
        ],
      },
    ],
    bands: [],
    legends: [{ id: "mobile", label: "Mobile" }],
    period_label: "Jun 16, 2026 (CST)",
    timezone: "CST",
  };
}

function rawEpochPayload(): ChartPayload {
  return {
    ...chartPayload(),
    x_axis: {
      ticks: [
        { value: "1781676000", label: "1781676000", position: 0 },
        { value: "1781686680", label: "1781686680", position: 1 },
      ],
    },
    series: [
      {
        id: "mobile",
        label: "Mobile",
        kind: "line",
        device: "mobile",
        visible: true,
        points: [
          { ts: "1781686200", label: "1781686200", value: 180 },
          { ts: "1781686680", label: "1781686680", value: 95 },
        ],
      },
    ],
    period_label: "1781676000 - 1781686680 CST",
  };
}
