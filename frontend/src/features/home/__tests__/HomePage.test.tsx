import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HomePage } from "../HomePage";
import { useAppStore } from "../../../shared/state/appStore";

type MockOptions = {
  defaultCountry?: string;
  countries?: Array<{
    code: string;
    has_data: boolean;
    raw_calls?: number;
    rows?: number;
  }>;
  empty?: boolean;
};

const requests: string[] = [];

describe("HomePage local dashboard", () => {
  beforeEach(() => {
    localStorage.clear();
    requests.length = 0;
    useAppStore.setState({
      activeCountry: "MX",
      hasCountryPreference: false,
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renderiza estado vacio sin datos", async () => {
    mockFetch({ empty: true });
    renderHome();

    expect(await screen.findByText("Dashboard General MX")).toBeInTheDocument();
    expect(
      await screen.findByText(
        "No local Parquet rows available for requested country.",
      ),
    ).toBeInTheDocument();
  });

  it("selecciona el unico pais con datos", async () => {
    mockFetch({
      defaultCountry: "ES",
      countries: [
        { code: "ES", has_data: true, raw_calls: 2, rows: 20 },
        { code: "MX", has_data: false },
        { code: "PE", has_data: false },
        { code: "CO", has_data: false },
        { code: "AR", has_data: false },
      ],
    });
    renderHome();

    expect(await screen.findByText("Dashboard General ES")).toBeInTheDocument();
  });

  it("cambia queries al cambiar el selector de pais", async () => {
    mockFetch();
    renderHome();
    const select = await screen.findByLabelText("Pais del dashboard");

    fireEvent.change(select, { target: { value: "PE" } });

    await waitFor(() => {
      expect(requests.some((request) => request.includes("country=PE"))).toBe(
        true,
      );
    });
  });

  it("muestra widgets y tabla de Resumen recibidos desde API", async () => {
    mockFetch();
    renderHome();

    expect(await screen.findByText("Paginas vistas")).toBeInTheDocument();
    expect(await screen.findByText("150")).toBeInTheDocument();
    expect(
      await screen.findByText("Detalle por App Name y Sistema operativo"),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText("portabilidad nomina").length).toBeGreaterThan(
        0,
      );
    });
  });

  it("search llama a API con query correcta", async () => {
    mockFetch();
    renderHome();
    const search = await screen.findByLabelText("Buscar en detalle");

    fireEvent.change(search, { target: { value: "porta" } });

    await waitFor(() => {
      expect(requests.some((request) => request.includes("search=porta"))).toBe(
        true,
      );
    });
  });

  it("sort por Page Views llama a API con sort correcto", async () => {
    mockFetch();
    renderHome();
    const sortButton = await screen.findByRole("button", {
      name: /Page Views/i,
    });

    fireEvent.click(sortButton);

    await waitFor(() => {
      expect(
        requests.some(
          (request) =>
            request.includes("/analytics/dashboard/summary/table") &&
            request.includes("sort=page_views"),
        ),
      ).toBe(true);
    });
  });

  it("tab Errores muestra widgets recibidos desde API", async () => {
    mockFetch();
    renderHome();

    fireEvent.click(await screen.findByRole("tab", { name: "Errores" }));

    expect(
      await screen.findByText("Comparativa de sesiones con error por App Name"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("% Sesiones con Error por App Name"),
    ).toBeInTheDocument();
  });

  it("Dimension abre, aplica y limpia dimension", async () => {
    mockFetch();
    renderHome();

    fireEvent.click(await screen.findByRole("button", { name: /Dimension/i }));
    fireEvent.click(await screen.findByRole("button", { name: "Browser" }));

    await waitFor(() => {
      expect(screen.getByText("Dimension: Browser")).toBeInTheDocument();
      expect(
        requests.some((request) => request.includes("dimension=browser")),
      ).toBe(true);
    });

    fireEvent.click(screen.getByRole("button", { name: /Dimension/i }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Quitar dimension" }),
    );

    expect(
      await screen.findByText("Dimension: sin dimension"),
    ).toBeInTheDocument();
  });

  it("Segmento abre, aplica y limpia segmento", async () => {
    mockFetch();
    renderHome();

    fireEvent.click(await screen.findByRole("button", { name: /Segmento/i }));
    fireEvent.click(
      await screen.findByRole("button", { name: /App Name: pagos/i }),
    );

    await waitFor(() => {
      expect(screen.getByText("Segmento: App Name: pagos")).toBeInTheDocument();
      expect(
        requests.some((request) =>
          request.includes("segment=app_name%3Apagos"),
        ),
      ).toBe(true);
    });

    fireEvent.click(screen.getByRole("button", { name: /Segmento/i }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Limpiar segmento" }),
    );

    expect(
      await screen.findByText("Segmento: sin segmento"),
    ).toBeInTheDocument();
  });

  it("no renderiza la Home antigua ni datos mock", async () => {
    mockFetch();
    renderHome();

    expect(await screen.findByText("Dashboard General MX")).toBeInTheDocument();
    expect(screen.queryByText("Raw calls")).not.toBeInTheDocument();
    expect(screen.queryByText("Cards")).not.toBeInTheDocument();
    expect(screen.queryByText("Datos ingestados")).not.toBeInTheDocument();
  });
});

function renderHome() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <HomePage />
    </QueryClientProvider>,
  );
}

function mockFetch(options: MockOptions = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input));
      requests.push(`${url.pathname}${url.search}`);
      const payload = responseFor(url, options);
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
}

function responseFor(url: URL, options: MockOptions) {
  const country =
    url.searchParams.get("country") ?? options.defaultCountry ?? "MX";
  if (url.pathname.endsWith("/analytics/countries")) {
    return {
      default_country: options.defaultCountry ?? "MX",
      countries: options.countries ?? [
        { code: "ES", label: "Espana", has_data: false, raw_calls: 0, rows: 0 },
        { code: "MX", label: "Mexico", has_data: true, raw_calls: 1, rows: 2 },
        { code: "PE", label: "Peru", has_data: false, raw_calls: 0, rows: 0 },
        {
          code: "CO",
          label: "Colombia",
          has_data: false,
          raw_calls: 0,
          rows: 0,
        },
        {
          code: "AR",
          label: "Argentina",
          has_data: false,
          raw_calls: 0,
          rows: 0,
        },
      ],
    };
  }
  if (url.pathname.endsWith("/analytics/dimensions")) {
    return {
      country,
      groups: [
        {
          label: "Page",
          items: [{ id: "app_name", label: "App Name", status: "available" }],
        },
        {
          label: "Device",
          items: [{ id: "browser", label: "Browser", status: "available" }],
        },
      ],
    };
  }
  if (url.pathname.endsWith("/analytics/segments")) {
    return {
      country,
      segments: [
        {
          id: "app_name:pagos",
          label: "App Name: pagos",
          field: "app_name",
          value: "pagos",
          count: 1,
        },
      ],
    };
  }
  if (options.empty) return emptyPayload(country);
  if (url.pathname.endsWith("/analytics/dashboard/summary/table")) {
    return {
      status: "ok",
      country,
      source: "parquet",
      columns: [
        { key: "name", label: "name", sortable: true },
        { key: "app_name", label: "App Name", sortable: true },
        { key: "operating_system", label: "Sistema operativo", sortable: true },
        { key: "page_views", label: "Page Views", sortable: true },
        { key: "sessions", label: "Sessions", sortable: true },
        { key: "conversions", label: "General - Conversiones", sortable: true },
      ],
      rows: [
        {
          name: "portabilidad nomina",
          app_name: "portabilidad nomina",
          operating_system: "iOS",
          page_views: 100,
          sessions: 20,
          conversions: 3,
        },
      ],
      available_datasets: ["country=MX/raw_api_calls"],
    };
  }
  if (url.pathname.endsWith("/analytics/dashboard/errors/table")) {
    return {
      status: "ok",
      country,
      source: "parquet",
      columns: [
        { key: "name", label: "App Name", sortable: true },
        { key: "sessions", label: "Sessions", sortable: true },
        {
          key: "sessions_with_error",
          label: "Sessions with Error",
          sortable: true,
        },
        {
          key: "error_session_percent",
          label: "% Sesiones con Error",
          sortable: true,
        },
      ],
      rows: [
        {
          name: "portabilidad nomina",
          sessions: 20,
          sessions_with_error: 4,
          error_session_percent: 20,
        },
      ],
      available_datasets: ["country=MX/raw_api_calls"],
    };
  }
  if (url.pathname.endsWith("/analytics/dashboard/errors")) {
    return {
      status: "ok",
      country,
      source: "parquet",
      widgets: [
        {
          id: "error_sessions_by_app_name",
          title: "Comparativa de sesiones con error por App Name",
          chart_type: "donut",
          total: 5,
          series: [{ name: "portabilidad nomina", value: 4, percent: 80 }],
        },
        {
          id: "error_session_percentage_by_app_name",
          title: "% Sesiones con Error por App Name",
          chart_type: "table",
          rows: [{ name: "portabilidad nomina", error_session_percent: 20 }],
        },
      ],
      available_datasets: ["country=MX/raw_api_calls"],
    };
  }
  return {
    status: "ok",
    country,
    source: "parquet",
    applied_dimension: url.searchParams.get("dimension")
      ? { id: url.searchParams.get("dimension"), label: "Browser" }
      : null,
    applied_segment: url.searchParams.get("segment")
      ? { id: url.searchParams.get("segment"), label: "App Name: pagos" }
      : null,
    widgets: [
      {
        id: "page_views",
        title: "Paginas vistas",
        value: 150,
        unit: "count",
        breakdown: [{ label: "Mobile", value: 150 }],
        timeseries: [
          { ts: "2026-06-01T00:00:00Z", value: 80 },
          { ts: "2026-06-02T00:00:00Z", value: 70 },
        ],
      },
      {
        id: "sessions",
        title: "Sesiones",
        value: 30,
        unit: "count",
        breakdown: [],
        timeseries: [],
      },
    ],
    available_datasets: ["country=MX/raw_api_calls"],
  };
}

function emptyPayload(country: string) {
  return {
    status: "empty",
    country,
    source: "parquet",
    reason: "No local Parquet rows available for requested country.",
    required_dataset: "raw_api_calls",
    available_datasets: [],
    widgets: [],
    columns: [],
    rows: [],
  };
}
