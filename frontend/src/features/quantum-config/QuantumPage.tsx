import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Database,
  Globe2,
  LayoutDashboard,
  Monitor,
  Palette,
  Plus,
  RefreshCw,
  Save,
  Settings2,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { apiGet, apiPost, apiPut } from "../../shared/api/client";
import {
  COUNTRY_OPTIONS,
  CountryCode,
  countryLabel,
} from "../../shared/countries";
import { ThemePreference, useAppStore } from "../../shared/state/appStore";

type QuantumCountryConfig = {
  country: CountryCode;
  base_url: string;
  enabled: boolean;
  is_default?: boolean;
  dashboard_resolved?: boolean;
  dashboards: QuantumDashboardConfig[];
};

type QuantumDashboardConfig = {
  dashboard_id: string;
  name: string;
  dashboard_type: string;
  team_id: string;
  summary_tab: number;
  errors_tab: number;
  is_default: boolean;
  is_manual: boolean;
  validated: boolean;
  validation_status: "not_tested" | "ok" | "ko";
  discovered_at?: string | null;
  widgets: QuantumWidgetConfig[];
};

type QuantumWidgetConfig = {
  role: string;
  title: string;
  widget_id: string;
  widget_type: "CHART" | "TABLE" | "DONUT" | "KPI" | "UNKNOWN";
  tab: "summary" | "errors";
  enabled: boolean;
  discovered_at?: string | null;
};

type QuantumConfig = {
  schema_version?: number;
  browser: "chrome" | "edge" | "safari" | "firefox";
  session_mode: "browser" | "manual";
  country: CountryCode;
  countries: QuantumCountryConfig[];
  verify_tls: boolean;
  ingestion_depth_days: number;
  theme_preference: ThemePreference;
};

export function QuantumPage() {
  const queryClient = useQueryClient();
  const themePreference = useAppStore((state) => state.themePreference);
  const setThemePreference = useAppStore((state) => state.setThemePreference);
  const config = useQuery({
    queryKey: ["quantum-config"],
    queryFn: async () =>
      normalizeConfig(await apiGet<QuantumConfig>("/config/quantum")),
  });
  const [form, setForm] = useState<QuantumConfig | null>(null);
  const [manualCookie, setManualCookie] = useState("");

  const current = form ?? config.data;
  const countryRows = current?.countries ?? [];
  const defaultCountryExists = countryRows.some(
    (row) => row.country === current?.country,
  );
  const depthDaysInvalid =
    !current ||
    !Number.isInteger(current.ingestion_depth_days) ||
    current.ingestion_depth_days < 1;

  const save = useMutation({
    mutationFn: (payload: QuantumConfig & { manual_cookie?: string }) =>
      apiPut<QuantumConfig>("/config/quantum", payload),
    onSuccess: (data) => {
      setForm(data);
      setManualCookie("");
      void queryClient.invalidateQueries({ queryKey: ["quantum-config"] });
    },
  });

  const testCountry = useMutation({
    mutationFn: (country: CountryCode) =>
      apiPost(`/quantum/discover-dashboard?country=${country}`),
    onSuccess: async () => {
      const result = await config.refetch();
      if (result.data) setForm(result.data);
      void queryClient.invalidateQueries({ queryKey: ["quantum-config"] });
    },
  });

  const testDashboard = useMutation({
    mutationFn: ({
      country,
      dashboardId,
    }: {
      country: CountryCode;
      dashboardId: string;
    }) =>
      apiPost(
        `/quantum/test-dashboard?country=${country}&dashboard_id=${encodeURIComponent(
          dashboardId,
        )}`,
      ),
    onSuccess: async () => {
      const result = await config.refetch();
      if (result.data) setForm(result.data);
      void queryClient.invalidateQueries({ queryKey: ["quantum-config"] });
    },
  });

  useEffect(() => {
    if (config.data?.theme_preference) {
      setThemePreference(config.data.theme_preference);
    }
  }, [config.data?.theme_preference, setThemePreference]);

  function update<K extends keyof QuantumConfig>(
    key: K,
    value: QuantumConfig[K],
  ) {
    if (!current) return;
    setForm({ ...current, [key]: value });
  }

  function updateCountryRow(
    index: number,
    patch: Partial<QuantumCountryConfig>,
  ) {
    if (!current) return;
    const countries = current.countries.map((row, rowIndex) =>
      rowIndex === index ? { ...row, ...patch } : row,
    );
    const country =
      current.country === current.countries[index]?.country && patch.country
        ? patch.country
        : current.country;
    setForm({ ...current, country, countries });
  }

  function addCountry() {
    if (!current) return;
    const nextCountry = COUNTRY_OPTIONS.find(
      (option) => !current.countries.some((row) => row.country === option.code),
    )?.code;
    if (!nextCountry) return;
    setForm({
      ...current,
      country: current.countries.length ? current.country : nextCountry,
      countries: [
        ...current.countries,
        emptyCountryConfig(nextCountry, current.countries.length === 0),
      ],
    });
  }

  function removeCountry(index: number) {
    if (!current) return;
    const countries = current.countries.filter(
      (_, rowIndex) => rowIndex !== index,
    );
    const country = countries.some((row) => row.country === current.country)
      ? current.country
      : (countries[0]?.country ?? current.country);
    setForm({ ...current, country, countries });
  }

  function updateDashboard(
    countryIndex: number,
    dashboardIndex: number,
    patch: Partial<QuantumDashboardConfig>,
  ) {
    if (!current) return;
    const countries = current.countries.map((countryRow, rowIndex) => {
      if (rowIndex !== countryIndex) return countryRow;
      const dashboards = countryRow.dashboards.map((dashboard, itemIndex) =>
        itemIndex === dashboardIndex ? { ...dashboard, ...patch } : dashboard,
      );
      return { ...countryRow, dashboards: normalizeDashboards(dashboards) };
    });
    setForm({ ...current, countries });
  }

  function addManualDashboard(countryIndex: number) {
    if (!current) return;
    const countries = current.countries.map((countryRow, rowIndex) => {
      if (rowIndex !== countryIndex) return countryRow;
      return {
        ...countryRow,
        dashboards: normalizeDashboards([
          ...(countryRow.dashboards ?? []),
          emptyDashboardConfig(),
        ]),
      };
    });
    setForm({ ...current, countries });
  }

  function removeDashboard(countryIndex: number, dashboardIndex: number) {
    if (!current) return;
    const countries = current.countries.map((countryRow, rowIndex) => {
      if (rowIndex !== countryIndex) return countryRow;
      return {
        ...countryRow,
        dashboards: normalizeDashboards(
          countryRow.dashboards.filter((_, index) => index !== dashboardIndex),
        ),
      };
    });
    setForm({ ...current, countries });
  }

  function setDefaultDashboard(countryIndex: number, dashboardIndex: number) {
    if (!current) return;
    const countries = current.countries.map((countryRow, rowIndex) => {
      if (rowIndex !== countryIndex) return countryRow;
      return {
        ...countryRow,
        dashboards: countryRow.dashboards.map((dashboard, index) => ({
          ...dashboard,
          is_default: index === dashboardIndex,
        })),
      };
    });
    setForm({ ...current, countries });
  }

  function updateWidget(
    countryIndex: number,
    dashboardIndex: number,
    role: string,
    enabled: boolean,
  ) {
    if (!current) return;
    const countries = current.countries.map((countryRow, rowIndex) => {
      if (rowIndex !== countryIndex) return countryRow;
      return {
        ...countryRow,
        dashboards: countryRow.dashboards.map((dashboard, index) =>
          index === dashboardIndex
            ? {
                ...dashboard,
                widgets: dashboard.widgets.map((widget) =>
                  widget.role === role ? { ...widget, enabled } : widget,
                ),
              }
            : dashboard,
        ),
      };
    });
    setForm({ ...current, countries });
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!current) return;
    save.mutate({
      ...current,
      country: defaultCountryExists
        ? current.country
        : (current.countries[0]?.country ?? current.country),
      countries: current.countries.map((row) => ({
        ...row,
        enabled: row.enabled,
        is_default: row.country === current.country,
        dashboards: normalizeDashboards(row.dashboards),
      })),
      manual_cookie:
        current.session_mode === "manual" ? manualCookie : undefined,
    });
  }

  if (!current) return <div className="empty">Cargando</div>;

  return (
    <>
      <header className="page-header config-page-header">
        <div>
          <span className="eyebrow">Configuracion local</span>
          <h1>Quantum</h1>
          <p>
            Conexiones, apariencia y widgets disponibles para la experiencia
            offline.
          </p>
        </div>
        <span className={`status ${defaultCountryExists ? "ok" : "ko"}`}>
          {defaultCountryExists ? "Default preparado" : "Define un default"}
        </span>
      </header>

      <form
        className="config-surface config-premium-surface"
        onSubmit={onSubmit}
      >
        <section className="config-panel config-control-panel">
          <div className="section-heading compact">
            <h2 className="heading-with-icon">
              <Settings2 size={18} aria-hidden="true" />
              Operativa local
            </h2>
          </div>
          <div className="config-control-grid">
            <label className="field config-field-card">
              <Monitor size={18} aria-hidden="true" />
              <span>Browser</span>
              <select
                value={current.browser}
                onChange={(event) =>
                  update(
                    "browser",
                    event.target.value as QuantumConfig["browser"],
                  )
                }
              >
                <option value="chrome">Chrome</option>
                <option value="edge">Edge</option>
                <option value="safari">Safari</option>
                <option value="firefox">Firefox</option>
              </select>
            </label>
            <label className="field config-field-card">
              <ShieldCheck size={18} aria-hidden="true" />
              <span>Sesion</span>
              <select
                value={current.session_mode}
                onChange={(event) =>
                  update(
                    "session_mode",
                    event.target.value as QuantumConfig["session_mode"],
                  )
                }
              >
                <option value="browser">Browser</option>
                <option value="manual">Manual</option>
              </select>
            </label>
            <label className="field config-field-card theme-select">
              <Palette size={18} aria-hidden="true" />
              <span>Tema</span>
              <select
                value={themePreference}
                onChange={(event) => {
                  const nextTheme = event.target.value as ThemePreference;
                  setThemePreference(nextTheme);
                  update("theme_preference", nextTheme);
                }}
              >
                <option value="system">Sistema</option>
                <option value="light">Claro</option>
                <option value="dark">Oscuro</option>
              </select>
            </label>
            <label className="field config-field-card">
              <Database size={18} aria-hidden="true" />
              <span>Profundidad de ingesta</span>
              <input
                type="number"
                min={1}
                max={3650}
                required
                value={current.ingestion_depth_days || ""}
                onChange={(event) =>
                  update(
                    "ingestion_depth_days",
                    event.target.value === "" ? 0 : Number(event.target.value),
                  )
                }
              />
              <small>dias</small>
            </label>
          </div>
        </section>

        <section className="config-panel config-country-panel">
          <div className="section-heading compact">
            <h2 className="heading-with-icon">
              <Globe2 size={18} aria-hidden="true" />
              Paises Quantum
            </h2>
            <button
              className="command-button"
              type="button"
              disabled={countryRows.length >= COUNTRY_OPTIONS.length}
              onClick={addCountry}
            >
              <Plus size={16} /> Anadir pais
            </button>
          </div>

          {countryRows.length ? (
            <div className="config-country-grid">
              {countryRows.map((row, index) => (
                <article
                  className="config-country-card"
                  key={`${row.country}-${index}`}
                >
                  <header>
                    <div className="config-country-title">
                      <span className="config-country-icon" aria-hidden="true">
                        <Globe2 size={18} />
                      </span>
                      <div>
                        <span className="eyebrow">Pais</span>
                        <strong>{countryLabel(row.country)}</strong>
                      </div>
                    </div>
                    <span className="status ok">Activo</span>
                  </header>
                  <div className="config-country-fields">
                    <label className="field">
                      <span>Pais</span>
                      <select
                        value={row.country}
                        aria-label={`Pais ${index + 1}`}
                        onChange={(event) =>
                          updateCountryRow(index, {
                            country: event.target.value as CountryCode,
                          })
                        }
                      >
                        {COUNTRY_OPTIONS.map((option) => (
                          <option
                            key={option.code}
                            value={option.code}
                            disabled={countryRows.some(
                              (candidate, rowIndex) =>
                                rowIndex !== index &&
                                candidate.country === option.code,
                            )}
                          >
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="field config-url-field">
                      <span>Base URL</span>
                      <input
                        value={row.base_url}
                        aria-label={`Base URL ${row.country}`}
                        onChange={(event) =>
                          updateCountryRow(index, {
                            base_url: event.target.value,
                          })
                        }
                      />
                    </label>
                  </div>
                  <footer>
                    <label className="config-default-toggle">
                      <input
                        type="checkbox"
                        checked={row.country === current.country}
                        aria-label={`Default ${row.country}`}
                        onChange={(event) =>
                          event.target.checked
                            ? update("country", row.country)
                            : undefined
                        }
                      />
                      <span>Default</span>
                    </label>
                    <div className="config-row-actions">
                      <button
                        className="command-button"
                        type="button"
                        disabled={!row.base_url || testCountry.isPending}
                        onClick={() => testCountry.mutate(row.country)}
                      >
                        <CheckCircle2 size={16} /> Test pais
                      </button>
                      <button
                        className="icon-button danger"
                        type="button"
                        aria-label={`Eliminar ${row.country}`}
                        title={`Eliminar ${row.country}`}
                        onClick={() => removeCountry(index)}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </footer>
                </article>
              ))}
            </div>
          ) : (
            <div className="empty compact">Sin paises configurados</div>
          )}
        </section>

        <section className="config-panel dashboard-config-panel">
          <div className="section-heading compact">
            <h2 className="heading-with-icon">
              <LayoutDashboard size={18} aria-hidden="true" />
              Dashboards por pais
            </h2>
          </div>
          <div className="dashboard-config-list">
            {countryRows.map((row, countryIndex) => (
              <article className="dashboard-config-item" key={row.country}>
                <header>
                  <div>
                    <span className="eyebrow">Pais</span>
                    <strong>{countryLabel(row.country)}</strong>
                  </div>
                  <button
                    className="command-button"
                    type="button"
                    onClick={() => addManualDashboard(countryIndex)}
                  >
                    <Plus size={16} /> Dashboard manual
                  </button>
                </header>
                {row.dashboards.length ? (
                  <div className="dashboard-card-stack">
                    {row.dashboards.map((dashboard, dashboardIndex) => (
                      <section
                        className="dashboard-config-card"
                        key={`${row.country}-${dashboard.dashboard_id || dashboardIndex}`}
                      >
                        <div className="dashboard-config-card-header">
                          <div>
                            <span className="eyebrow">
                              {dashboard.is_manual ? "Manual" : "Default"}
                            </span>
                            <h3>
                              {dashboard.name ||
                                (dashboard.is_manual
                                  ? "Dashboard manual"
                                  : "Dashboard default")}
                            </h3>
                          </div>
                          <span
                            className={`status ${
                              dashboard.validated ? "ok" : "ko"
                            }`}
                          >
                            {dashboard.validated ? "Validado" : "Pendiente"}
                          </span>
                        </div>
                        <div className="dashboard-fields-grid">
                          <label className="field">
                            <span>Dashboard ID</span>
                            <input
                              value={dashboard.dashboard_id}
                              readOnly={
                                !dashboard.is_manual || dashboard.validated
                              }
                              onChange={(event) =>
                                updateDashboard(countryIndex, dashboardIndex, {
                                  dashboard_id: event.target.value,
                                  validated: false,
                                  validation_status: "not_tested",
                                })
                              }
                            />
                          </label>
                          <label className="field">
                            <span>Nombre</span>
                            <input
                              value={dashboard.name}
                              onChange={(event) =>
                                updateDashboard(countryIndex, dashboardIndex, {
                                  name: event.target.value,
                                })
                              }
                            />
                          </label>
                          <label className="field">
                            <span>Tipo</span>
                            <input value={dashboard.dashboard_type} readOnly />
                          </label>
                          <label className="field">
                            <span>Team ID</span>
                            <input value={dashboard.team_id} readOnly />
                          </label>
                        </div>
                        <div className="config-row-actions dashboard-actions-row">
                          <label className="config-default-toggle">
                            <input
                              type="checkbox"
                              checked={dashboard.is_default}
                              onChange={(event) =>
                                event.target.checked
                                  ? setDefaultDashboard(
                                      countryIndex,
                                      dashboardIndex,
                                    )
                                  : undefined
                              }
                            />
                            <span>Default del pais</span>
                          </label>
                          {dashboard.is_manual && !dashboard.validated && (
                            <button
                              className="command-button"
                              type="button"
                              disabled={
                                !dashboard.dashboard_id ||
                                testDashboard.isPending
                              }
                              onClick={() =>
                                testDashboard.mutate({
                                  country: row.country,
                                  dashboardId: dashboard.dashboard_id,
                                })
                              }
                            >
                              <RefreshCw size={16} /> Test dashboard
                            </button>
                          )}
                          {dashboard.is_manual && (
                            <button
                              className="icon-button danger"
                              type="button"
                              aria-label="Borrar dashboard manual"
                              title="Borrar dashboard manual"
                              onClick={() =>
                                removeDashboard(countryIndex, dashboardIndex)
                              }
                            >
                              <Trash2 size={16} />
                            </button>
                          )}
                        </div>
                        <div className="widget-config-section-grid">
                          {WIDGET_CONFIG_GROUPS.map((group) => {
                            const widgets = dashboard.widgets.filter(
                              (widget) => widget.tab === group.tab,
                            );
                            return (
                              <section
                                className="widget-config-group"
                                key={`${row.country}-${dashboardIndex}-${group.title}`}
                              >
                                <h4>{group.title}</h4>
                                <div className="widget-config-grid">
                                  {widgets.map((widget) => (
                                    <label
                                      className="widget-config-row"
                                      key={`${dashboard.dashboard_id}-${widget.role}`}
                                    >
                                      <input
                                        type="checkbox"
                                        checked={widget.enabled}
                                        onChange={(event) =>
                                          updateWidget(
                                            countryIndex,
                                            dashboardIndex,
                                            widget.role,
                                            event.target.checked,
                                          )
                                        }
                                      />
                                      <span>
                                        <strong>{widget.title}</strong>
                                        <small>
                                          id: {widget.widget_id || widget.role}
                                        </small>
                                      </span>
                                      <em>{widget.widget_type}</em>
                                    </label>
                                  ))}
                                </div>
                              </section>
                            );
                          })}
                        </div>
                      </section>
                    ))}
                  </div>
                ) : (
                  <div className="empty compact">
                    Ejecuta Test pais o anade un dashboard manual.
                  </div>
                )}
              </article>
            ))}
          </div>
        </section>

        {current.session_mode === "manual" && (
          <section className="config-panel">
            <label className="field">
              <span>Cookie manual</span>
              <textarea
                value={manualCookie}
                onChange={(event) => setManualCookie(event.target.value)}
                autoComplete="off"
              />
            </label>
          </section>
        )}

        <div className="config-actions">
          <button
            className="button"
            type="submit"
            disabled={save.isPending || !countryRows.length || depthDaysInvalid}
          >
            <Save size={16} /> Guardar
          </button>
        </div>
      </form>
    </>
  );
}

const WIDGET_CONFIG_GROUPS = [
  {
    title: "Resumen",
    tab: "summary" as const,
  },
  {
    title: "Errores",
    tab: "errors" as const,
  },
];

function emptyCountryConfig(
  country: CountryCode,
  enabled = true,
): QuantumCountryConfig {
  return {
    country,
    base_url: "",
    enabled,
    dashboard_resolved: false,
    dashboards: [],
  };
}

function emptyDashboardConfig(): QuantumDashboardConfig {
  return {
    dashboard_id: "",
    name: "Dashboard manual",
    dashboard_type: "Quantum dashboard",
    team_id: "",
    summary_tab: 0,
    errors_tab: 1,
    is_default: false,
    is_manual: true,
    validated: false,
    validation_status: "not_tested",
    widgets: defaultWidgetConfig(),
  };
}

function defaultWidgetConfig(): QuantumWidgetConfig[] {
  return [
    widget("summary.page_views", "Paginas vistas", "CHART", "summary"),
    widget("summary.sessions", "Sesiones", "CHART", "summary"),
    widget(
      "summary.converted_sessions",
      "Sesiones con conversion",
      "CHART",
      "summary",
    ),
    widget(
      "summary.avg_session_duration",
      "Tiempo medio de sesion",
      "CHART",
      "summary",
    ),
    widget(
      "summary.detail_by_app_name_os",
      "Detalle App Name / SO",
      "TABLE",
      "summary",
    ),
    widget(
      "errors.error_sessions_percentage_evolution",
      "% sesiones con error",
      "CHART",
      "errors",
    ),
    widget("errors.top_errors_by_error_name", "Top errores", "TABLE", "errors"),
    widget(
      "errors.error_sessions_by_app_name_comparison",
      "Comparativa App Name",
      "DONUT",
      "errors",
    ),
    widget(
      "errors.error_session_percentage_by_app_name",
      "% error por App Name",
      "TABLE",
      "errors",
    ),
  ];
}

function widget(
  role: string,
  title: string,
  widgetType: QuantumWidgetConfig["widget_type"],
  tab: QuantumWidgetConfig["tab"],
): QuantumWidgetConfig {
  return {
    role,
    title,
    widget_id: `role:${role}`,
    widget_type: widgetType,
    tab,
    enabled: true,
  };
}

function normalizeDashboards(
  dashboards: QuantumDashboardConfig[] = [],
): QuantumDashboardConfig[] {
  if (!dashboards.length) return dashboards;
  const defaultIndex = dashboards.findIndex(
    (dashboard) => dashboard.is_default,
  );
  const resolvedDefault = defaultIndex >= 0 ? defaultIndex : 0;
  return dashboards.map((dashboard, index) => ({
    ...dashboard,
    is_default: index === resolvedDefault,
    widgets: dashboard.widgets?.length
      ? dashboard.widgets
      : defaultWidgetConfig(),
  }));
}

type LegacyCountryConfig = Partial<QuantumCountryConfig> & {
  country: CountryCode;
  dashboard_id?: string;
  team_id?: string;
  tab?: number;
};

function normalizeConfig(config: QuantumConfig): QuantumConfig {
  const countries = (config.countries ?? []).map(normalizeCountryConfig);
  return {
    browser: config.browser ?? "chrome",
    session_mode: config.session_mode ?? "browser",
    country: countries.some((row) => row.country === config.country)
      ? config.country
      : (countries[0]?.country ?? "MX"),
    countries,
    verify_tls: config.verify_tls ?? true,
    ingestion_depth_days: Number.isInteger(config.ingestion_depth_days)
      ? config.ingestion_depth_days
      : 30,
    theme_preference: config.theme_preference ?? "system",
    schema_version: config.schema_version,
  };
}

function normalizeCountryConfig(
  row: LegacyCountryConfig,
): QuantumCountryConfig {
  return {
    country: row.country,
    base_url: row.base_url ?? "",
    enabled: row.enabled ?? true,
    is_default: row.is_default ?? false,
    dashboard_resolved: row.dashboard_resolved ?? Boolean(row.dashboard_id),
    dashboards: normalizeDashboards(
      row.dashboards?.length ? row.dashboards : legacyDashboardConfig(row),
    ),
  };
}

function legacyDashboardConfig(
  row: LegacyCountryConfig,
): QuantumDashboardConfig[] {
  if (!row.dashboard_id) return [];
  return [
    {
      dashboard_id: row.dashboard_id,
      name: "Dashboard default",
      dashboard_type: "Quantum dashboard",
      team_id: row.team_id ?? "",
      summary_tab: row.tab ?? 0,
      errors_tab: 1,
      is_default: true,
      is_manual: false,
      validated: true,
      validation_status: "ok",
      widgets: defaultWidgetConfig(),
    },
  ];
}
