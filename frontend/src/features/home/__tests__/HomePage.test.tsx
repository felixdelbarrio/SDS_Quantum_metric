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
    label?: string;
    has_data: boolean;
    raw_calls?: number;
    rows?: number;
  }>;
  empty?: boolean;
  missingDays?: string[];
};

const requests: string[] = [];
const postBodies: unknown[] = [];

describe("HomePage local dashboard", () => {
  beforeEach(() => {
    localStorage.clear();
    requests.length = 0;
    postBodies.length = 0;
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
        "No hay datos locales reproducibles. Ejecuta una ingesta o una regresion para capturar las cards obligatorias.",
      ),
    ).toBeInTheDocument();
  });

  it("selecciona el unico pais con datos", async () => {
    mockFetch({
      defaultCountry: "ES",
      countries: [
        { code: "ES", label: "Espana", has_data: true, raw_calls: 2, rows: 20 },
      ],
    });
    renderHome();

    expect(await screen.findByText("Dashboard General ES")).toBeInTheDocument();
  });

  it("cambia queries al cambiar el selector de pais", async () => {
    mockFetch({
      countries: [
        { code: "MX", label: "Mexico", has_data: true, raw_calls: 1, rows: 2 },
        { code: "PE", label: "Peru", has_data: true, raw_calls: 1, rows: 2 },
      ],
    });
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
    const today = todayInMexico();

    expect(await screen.findByText("Paginas vistas")).toBeInTheDocument();
    expect((await screen.findAllByText("150")).length).toBeGreaterThan(0);
    expect(await screen.findAllByText("Jun 16, 2026 (CST)")).not.toHaveLength(
      0,
    );
    expect(
      requests.some(
        (request) =>
          request.includes("range_key=last_7_days") &&
          request.includes(`start_date=${addDays(today, -6)}`) &&
          request.includes(`end_date=${today}`),
      ),
    ).toBe(true);
    expect(
      await screen.findByText("Detalle por App Name y Sistema operativo"),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText("portabilidad nomina").length).toBeGreaterThan(
        0,
      );
    });
  });

  it("no muestra KPIs tecnicos ni boton Actualizar en Dashboard", async () => {
    mockFetch();
    renderHome();

    expect(await screen.findByText("Dashboard General MX")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Actualizar/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/calls/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/filas/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/cards/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/passed/i)).not.toBeInTheDocument();
  });

  it("muestra coverage incompleta y lanza ingesta de dias faltantes", async () => {
    mockFetch({ missingDays: ["2026-06-17"] });
    renderHome();

    expect(
      await screen.findByText(
        "Falta 1 dia para completar el periodo: 2026-06-17.",
      ),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Ingestar periodo" }));

    await waitFor(() => {
      expect(
        requests.some(
          (request) => request === "POST /api/ingestions/missing-days",
        ),
      ).toBe(true);
    });
    expect(postBodies[0]).toMatchObject({
      range_key: "last_7_days",
      start_date: addDays(todayInMexico(), -6),
      end_date: todayInMexico(),
    });
  });

  it("solicita Yesterday y Last 7 Days con range_key explicito", async () => {
    mockFetch();
    renderHome();
    const selector = await screen.findByLabelText("Fecha");

    fireEvent.change(selector, { target: { value: "yesterday" } });

    await waitFor(() => {
      expect(
        requests.some(
          (request) =>
            request.includes("/local-dashboard/summary") &&
            request.includes("range_key=yesterday"),
        ),
      ).toBe(true);
    });

    fireEvent.change(selector, { target: { value: "last_7_days" } });

    await waitFor(() => {
      expect(
        requests.some(
          (request) =>
            request.includes("/local-dashboard/summary") &&
            request.includes("range_key=last_7_days"),
        ),
      ).toBe(true);
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
            request.includes("/local-dashboard/summary/table") &&
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
      await screen.findByText("Evolutivo - % Sesiones con Error"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Top 20 Errores por nombre del error"),
    ).toBeInTheDocument();
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

function todayInMexico() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Mexico_City",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const part = (type: string) =>
    parts.find((candidate) => candidate.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

function addDays(value: string, days: number) {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function mockFetch(options: MockOptions = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const rawUrl =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.toString()
            : input.url;
      const url = new URL(rawUrl, "http://localhost");
      const method = init?.method ?? "GET";
      requests.push(
        method === "GET"
          ? `${url.pathname}${url.search}`
          : `${method} ${url.pathname}`,
      );
      if (method !== "GET" && init?.body) {
        postBodies.push(JSON.parse(String(init.body)));
      }
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
  if (url.pathname.endsWith("/local-dashboard/countries")) {
    if (options.empty) {
      return {
        default_country: options.defaultCountry ?? "MX",
        countries: [],
      };
    }
    return {
      default_country: options.defaultCountry ?? "MX",
      countries: options.countries ?? [
        { code: "MX", label: "Mexico", has_data: true, raw_calls: 1, rows: 2 },
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
  if (url.pathname.endsWith("/local-dashboard/coverage")) {
    const missingDays = options.missingDays ?? [];
    return {
      country,
      start: url.searchParams.get("start"),
      end: url.searchParams.get("end"),
      complete: missingDays.length === 0,
      warning_level: missingDays.length ? "warning" : "none",
      completeness: missingDays.length ? "empty" : "complete",
      covered_days: missingDays.length ? [] : [url.searchParams.get("start")],
      missing_days: missingDays,
      message: missingDays.length
        ? "Falta 1 dia para completar el periodo: 2026-06-17."
        : "Periodo completo en Parquet.",
    };
  }
  if (url.pathname.endsWith("/api/ingestions/missing-days")) {
    return { ingestion_id: "missing-days", status: "pending" };
  }
  if (options.empty) return emptyPayload(country);
  if (url.pathname.endsWith("/local-dashboard/summary/table")) {
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
  if (url.pathname.endsWith("/local-dashboard/errors/app-name")) {
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
  if (url.pathname.endsWith("/local-dashboard/errors/top-errors")) {
    return {
      status: "ok",
      country,
      source: "parquet",
      columns: [
        { key: "name", label: "Error Name", sortable: true },
        {
          key: "error_sessions",
          label: "General - Sesiones con error",
          sortable: true,
        },
        {
          key: "error_session_percent",
          label: "General - % Sesiones con error",
          sortable: true,
        },
      ],
      rows: [
        {
          name: "TypeError",
          error_name: "TypeError",
          error_sessions: 4,
          error_session_percent: 20,
        },
      ],
      available_datasets: ["country=MX/derived/errors_top_errors_table"],
    };
  }
  if (url.pathname.endsWith("/local-dashboard/errors")) {
    return {
      status: "ok",
      country,
      source: "parquet",
      widgets: [
        {
          id: "error_sessions_percentage_evolution",
          title: "Evolutivo - % Sesiones con Error",
          value: 20,
          unit: "percent",
          breakdown: [{ label: "Mobile", value: 20 }],
          timeseries: [
            { ts: "2026-06-16T00:00:00Z", value: 20 },
            { ts: "2026-06-16T01:00:00Z", value: 21 },
          ],
          chart_payload: chartPayload("percent"),
          period: { label: "Jun 16, 2026 (CST)" },
        },
        {
          id: "error_sessions_by_app_name",
          title: "Comparativa de sesiones con error por App Name",
          chart_type: "donut",
          total: 5,
          series: [{ name: "portabilidad nomina", value: 4, percent: 80 }],
          chart_payload: donutPayload(),
          period: { label: "Jun 16, 2026 (CST)" },
        },
        {
          id: "error_session_percentage_by_app_name",
          title: "% Sesiones con Error por App Name",
          chart_type: "table",
          rows: [{ name: "portabilidad nomina", error_session_percent: 20 }],
        },
      ],
      available_datasets: ["country=MX/derived/errors_widgets"],
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
          { ts: "2026-06-16T00:00:00Z", value: 80 },
          { ts: "2026-06-16T01:00:00Z", value: 70 },
        ],
        chart_payload: chartPayload("count"),
        period: { label: "Jun 16, 2026 (CST)" },
      },
      {
        id: "sessions",
        title: "Sesiones",
        value: 30,
        unit: "count",
        breakdown: [],
        timeseries: [],
        chart_payload: chartPayload("count"),
        period: { label: "Jun 16, 2026 (CST)" },
      },
    ],
    available_datasets: ["country=MX/raw_api_calls"],
  };
}

function chartPayload(unit: "count" | "percent") {
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
      max: unit === "percent" ? 100 : 100,
      unit,
      ticks: [
        { value: 0, label: unit === "percent" ? "0%" : "0", position: 0 },
        { value: 50, label: unit === "percent" ? "50%" : "50", position: 0.5 },
        { value: 100, label: unit === "percent" ? "100%" : "100", position: 1 },
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
          { ts: "2026-06-16T00:00:00Z", label: "00:00", value: 80 },
          { ts: "2026-06-16T01:00:00Z", label: "01:00", value: 70 },
        ],
      },
      {
        id: "desktop",
        label: "Desktop",
        kind: "line",
        device: "desktop",
        visible: true,
        points: [
          { ts: "2026-06-16T00:00:00Z", label: "00:00", value: 0 },
          { ts: "2026-06-16T01:00:00Z", label: "01:00", value: 0 },
        ],
      },
    ],
    bands: [],
    legends: [
      { id: "mobile", label: "Mobile" },
      { id: "desktop", label: "Desktop" },
    ],
    period_label: "Jun 16, 2026 (CST)",
    timezone: "CST",
  };
}

function donutPayload() {
  return {
    chart_type: "donut",
    x_axis: { ticks: [] },
    y_axis: { ticks: [], min: 0, max: 5, unit: "count" },
    series: [
      {
        id: "segments",
        label: "Comparativa",
        kind: "bar",
        device: "unknown",
        visible: true,
        points: [{ label: "portabilidad nomina", value: 4 }],
      },
    ],
    bands: [],
    legends: [{ id: "portabilidad nomina", label: "portabilidad nomina" }],
    period_label: "Jun 16, 2026 (CST)",
    timezone: "CST",
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
