import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DatasetsPage } from "./DatasetsPage";

describe("DatasetsPage export", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("muestra el ZIP creado por backend", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/datasets")) {
        return json({
          data_dir: "/tmp/data",
          datasets: [
            {
              status: "ok",
              country: "MX",
              label: "Mexico",
              files: 1,
              bytes: 200,
              raw_calls: 9,
              rows: 100,
              cards: 9,
              regression_status: "passed",
            },
          ],
        });
      }
      if (url.endsWith("/api/datasets/MX/entities/raw_api_calls")) {
        return json({
          country: "MX",
          entity: "raw_api_calls",
          rows: [],
          columns: [],
          total: 0,
          offset: 0,
          limit: 100,
          source: "parquet",
        });
      }
      if (url.endsWith("/api/datasets/MX/entities")) {
        return json({
          country: "MX",
          entities: [
            {
              id: "raw_api_calls",
              label: "raw_api_calls",
              rows: 0,
              bytes: 0,
              path: "/tmp/data/MX/raw_api_calls.parquet",
            },
          ],
        });
      }
      if (method === "POST" && url.endsWith("/api/datasets/export")) {
        return json({
          status: "exported",
          path: "/Users/test/Downloads/sds-quantum-metric-export-MX.zip",
          filename: "sds-quantum-metric-export-MX.zip",
          size_bytes: 1234,
        });
      }
      return json({});
    });

    renderDatasets();

    fireEvent.click(await screen.findByLabelText("Exportar MX"));

    await waitFor(() => {
      expect(
        screen.getByText("sds-quantum-metric-export-MX.zip"),
      ).toBeInTheDocument();
      expect(
        screen.getByText(
          "/Users/test/Downloads/sds-quantum-metric-export-MX.zip",
        ),
      ).toBeInTheDocument();
    });
  });

  it("muestra carga inicial antes de declarar datasets vacios", async () => {
    let resolveDatasets: (response: Response) => void = () => undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/api/datasets")) {
        return new Promise<Response>((resolve) => {
          resolveDatasets = resolve;
        });
      }
      return json({});
    });

    renderDatasets();

    expect(screen.getByRole("status")).toHaveTextContent("Cargando datasets");
    expect(screen.queryByText("Sin datos ingestados")).not.toBeInTheDocument();

    resolveDatasets(
      new Response(JSON.stringify({ data_dir: "/tmp/data", datasets: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    expect(await screen.findByText("Sin datos ingestados")).toBeInTheDocument();
  });
});

function renderDatasets() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <DatasetsPage />
    </QueryClientProvider>,
  );
}

function json(body: unknown) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
}
