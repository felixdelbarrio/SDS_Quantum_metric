import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DatasetsPage } from "./DatasetsPage";

describe("DatasetsPage", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("no renderiza acciones manuales de mantenimiento", async () => {
    mockFetch();
    renderDatasets();

    expect(await screen.findByText("Datasets")).toBeInTheDocument();
    expect(screen.queryByText("Auditar")).not.toBeInTheDocument();
    expect(screen.queryByText("Regenerar derivados")).not.toBeInTheDocument();
    expect(screen.queryByText("Ejecutar regresion")).not.toBeInTheDocument();
  });
});

function renderDatasets() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <DatasetsPage />
    </QueryClientProvider>,
  );
}

function mockFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input));
      return new Response(JSON.stringify(payloadFor(url)), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
}

function payloadFor(url: URL) {
  if (url.pathname === "/api/datasets") {
    return {
      data_dir: "/tmp/qm",
      legacy_data_detected: false,
      datasets: [
        {
          status: "ok",
          country: "MX",
          label: "Mexico",
          files: 3,
          bytes: 2048,
          updated_at: "2026-06-16T00:00:00Z",
          raw_calls: 79,
          rows: 236,
          cards: 9,
          mandatory_cards: 9,
          mandatory_cards_captured: 9,
          summary_ready: true,
          errors_ready: true,
          derived_datasets: 6,
          regression_status: "passed",
          kpis: [],
          top_apps: [],
          top_errors: [],
        },
      ],
    };
  }
  if (url.pathname === "/api/datasets/MX/entities") {
    return {
      country: "MX",
      entities: [
        {
          id: "raw_api_calls",
          label: "RAW Calls",
          rows: 1,
          files: 1,
          bytes: 10,
        },
      ],
    };
  }
  if (url.pathname === "/api/datasets/MX/entities/raw_api_calls") {
    return {
      country: "MX",
      entity: "raw_api_calls",
      rows: [{ card_id: "card-1" }],
      columns: ["card_id"],
      total: 1,
    };
  }
  return {};
}
