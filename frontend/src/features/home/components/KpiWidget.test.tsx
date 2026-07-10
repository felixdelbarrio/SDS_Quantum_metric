import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { KpiWidget as KpiWidgetContract } from "../types";
import { KpiWidget } from "./KpiWidget";

describe("KpiWidget exact contracts", () => {
  it.each([
    ["Experience Health", 9.3, "score", 1, "9.3"],
    ["Navigation Error Rate", 9.9, "percent", 2, "9.90%"],
    ["Task Success Rate", 76.45, "percent", 2, "76.45%"],
  ] as const)(
    "renders exact display for %s",
    (title, value, unit, precision, formatted) => {
      render(
        <KpiWidget
          widget={widget({
            title,
            display: {
              raw_value: value,
              display_value: value,
              unit,
              scale: 1,
              precision,
              formatted,
            },
          })}
        />,
      );

      expect(screen.getByText(formatted)).toBeInTheDocument();
    },
  );

  it("uses exact comparison and table labels", () => {
    render(
      <KpiWidget
        widget={widget({
          title: "Top Navigation Errors",
          display: null,
          comparison: {
            label: "vs Historical Range",
            raw_delta: 1.5,
            display_delta: 1.5,
            precision: 1,
            formatted: "+1.5%",
            semantic_intent: "positive",
          },
          table: {
            columns: [
              {
                key: "count",
                label: "Exact Quantum Header",
                data_type: "number",
                precision: 0,
                sortable: true,
              },
            ],
            rows: [{ count: 746 }],
            period_label: "Jul 01, 2026 (COT)",
            timezone: "America/Bogota",
          },
        })}
      />,
    );

    expect(screen.getByText("+1.5%")).toHaveClass("metric-delta-good");
    expect(screen.getByText("vs Historical Range")).toBeInTheDocument();
    expect(screen.getByText("Exact Quantum Header")).toBeInTheDocument();
    expect(screen.getByText("746")).toBeInTheDocument();
  });
});

function widget(overrides: Partial<KpiWidgetContract>): KpiWidgetContract {
  return {
    id: "widget",
    widget_id: "widget",
    role: "generic.0.chart.widget",
    title: "Widget",
    display: null,
    unit: "count",
    breakdown: [],
    timeseries: [],
    chart: null,
    table: null,
    ...overrides,
  };
}
