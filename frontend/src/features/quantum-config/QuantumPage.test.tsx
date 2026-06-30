import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QuantumPage } from "./QuantumPage";
import { useAppStore } from "../../shared/state/appStore";

const initialState = useAppStore.getInitialState();

describe("QuantumPage configuration", () => {
  beforeEach(() => {
    localStorage.clear();
    useAppStore.setState(initialState, true);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("muestra selector de dashboards reales y widgets dinamicos", async () => {
    mockFetch();
    renderConfig();

    const countryLabel = (await screen.findAllByText("Mexico")).find((item) =>
      item.closest(".config-country-card"),
    );
    expect(countryLabel).toBeDefined();
    expect(
      within(countryLabel!.closest("article")!).queryByText("Dashboard"),
    ).toBeNull();
    expect(await screen.findAllByText("Dashboard General MX")).toHaveLength(2);
    expect(await screen.findByDisplayValue("dash-default")).toBeInTheDocument();
    expect(await screen.findByDisplayValue("~/Downloads")).toBeInTheDocument();
    expect(
      await screen.findByText("Sesion controlada de la aplicacion"),
    ).toBeInTheDocument();
    expect(await screen.findByText("CHART")).toBeInTheDocument();
    expect(await screen.findByText("id: card-page-views")).toBeInTheDocument();
    expect(screen.queryByText(/Dashboard manual/i)).toBeNull();
  });

  it("renderiza configuracion legacy sin dashboards sin pantalla en blanco", async () => {
    mockFetch({
      browser: "chrome",
      session_mode: "controlled",
      country: "MX",
      countries: [
        {
          country: "MX",
          base_url: "https://bbvamx.quantummetric.com",
          enabled: true,
          dashboard_resolved: true,
        },
      ],
      verify_tls: true,
      ingestion_depth_days: 7,
      theme_preference: "light",
    });
    renderConfig();

    expect(await screen.findByText("Quantum")).toBeInTheDocument();
    expect((await screen.findAllByText("Mexico")).length).toBeGreaterThan(0);
    expect(
      await screen.findByText(/Actualiza dashboards para seleccionar/i),
    ).toBeInTheDocument();
  });

  it("no permite guardar un pais activo sin dashboard default", async () => {
    mockFetch({
      ...defaultQuantumConfig(),
      countries: [
        {
          ...defaultQuantumConfig().countries[0],
          dashboards: [
            {
              ...defaultQuantumConfig().countries[0].dashboards[0],
              is_default: false,
            },
          ],
        },
      ],
    });
    renderConfig();

    expect(
      await screen.findByText(/Selecciona un dashboard default/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Guardar/i })).toBeDisabled();
  });
});

function renderConfig() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <QuantumPage />
    </QueryClientProvider>,
  );
}

function mockFetch(body: unknown = defaultQuantumConfig()) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/api/config/quantum")) {
      return json(body);
    }
    return json({});
  });
}

function defaultQuantumConfig() {
  return {
    browser: "chrome",
    session_mode: "controlled",
    country: "MX",
    countries: [
      {
        country: "MX",
        base_url: "https://bbvamx.quantummetric.com",
        enabled: true,
        is_default: true,
        dashboard_resolved: true,
        dashboards: [
          {
            dashboard_id: "dash-default",
            name: "Dashboard General MX",
            dashboard_type: "Quantum dashboard",
            team_id: "team",
            summary_tab: 0,
            errors_tab: 1,
            is_default: true,
            is_manual: false,
            validated: true,
            validation_status: "ok",
            source: "quantum_web",
            tabs: [
              {
                tab_index: 0,
                name: "Resumen",
                normalized_role: "summary",
              },
            ],
            widgets: [
              {
                role: "summary.page_views",
                title: "Paginas vistas",
                widget_id: "card-page-views",
                widget_type: "CHART",
                tab: "summary",
                tab_name: "Resumen",
                tab_index: 0,
                enabled: true,
                required: true,
                supported: true,
              },
            ],
          },
        ],
      },
    ],
    verify_tls: true,
    ingestion_depth_days: 30,
    theme_preference: "dark",
    export_path: "~/Downloads",
  };
}

function json(body: unknown) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
}
