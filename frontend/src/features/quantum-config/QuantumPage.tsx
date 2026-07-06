import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Database,
  FolderDown,
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
  X,
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
  source?: "quantum_api" | "quantum_web" | "config_cache" | "manual";
  discovered_at?: string | null;
  last_structure_at?: string | null;
  tabs: QuantumDashboardTabConfig[];
  widgets: QuantumWidgetConfig[];
};

type QuantumDashboardTabConfig = {
  tab_id?: string | null;
  tab_index: number;
  name: string;
  normalized_role?: string | null;
};

type QuantumWidgetConfig = {
  role: string;
  title: string;
  widget_id: string;
  card_id?: string | null;
  widget_type: "CHART" | "TABLE" | "DONUT" | "KPI" | "UNKNOWN";
  tab_id?: string | null;
  tab: string;
  tab_name: string;
  tab_index: number;
  enabled: boolean;
  required?: boolean;
  supported?: boolean;
  source?: "quantum_api" | "quantum_web" | "config_cache";
  discovered_at?: string | null;
};

type DashboardStructureResponse = {
  tabs: QuantumDashboardTabConfig[];
  widgets: QuantumWidgetConfig[];
};

type ManualDashboardPayload = {
  url: string;
  name: string;
};

type QuantumConfig = {
  schema_version?: number;
  browser: "chrome" | "edge" | "safari" | "firefox";
  session_mode: "controlled" | "browser" | "manual";
  country: CountryCode;
  countries: QuantumCountryConfig[];
  verify_tls: boolean;
  ingestion_depth_days: number;
  theme_preference: ThemePreference;
  export_path: string;
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
  const [manualDashboardOpen, setManualDashboardOpen] = useState(false);
  const [manualDashboard, setManualDashboard] =
    useState<ManualDashboardPayload>({
      url: "",
      name: "",
    });

  const current = form ?? config.data;
  const countryRows = current?.countries ?? [];
  const selectedCountryIndex = Math.max(
    0,
    countryRows.findIndex((row) => row.country === current?.country),
  );
  const selectedCountry = countryRows[selectedCountryIndex];
  const selectedDashboard = selectedCountry?.dashboards.find(
    (dashboard) => dashboard.is_default,
  );
  const selectedDashboardIndex = selectedDashboard
    ? (selectedCountry?.dashboards.findIndex(
        (dashboard) =>
          dashboard.dashboard_id === selectedDashboard.dashboard_id,
      ) ?? -1)
    : -1;
  const defaultCountryExists = countryRows.some(
    (row) => row.country === current?.country,
  );
  const depthDaysInvalid =
    !current ||
    !Number.isInteger(current.ingestion_depth_days) ||
    current.ingestion_depth_days < 1;
  const countriesMissingDefault =
    current?.countries.filter(
      (row) =>
        row.enabled &&
        !row.dashboards.some(
          (dashboard) => dashboard.is_default && dashboard.dashboard_id,
        ),
    ) ?? [];
  const canSaveConfig =
    Boolean(current) &&
    countryRows.length > 0 &&
    !depthDaysInvalid &&
    countriesMissingDefault.length === 0;

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
      apiPost(`/quantum/test-connection?country=${country}`),
    onSuccess: async () => {
      const result = await config.refetch();
      if (result.data) setForm(result.data);
      void queryClient.invalidateQueries({ queryKey: ["quantum-config"] });
    },
  });

  const refreshDashboards = useMutation({
    mutationFn: (country: CountryCode) =>
      apiPost(`/quantum/countries/${country}/dashboards/refresh`),
    onSuccess: async () => {
      const result = await config.refetch();
      if (result.data) setForm(result.data);
      void queryClient.invalidateQueries({ queryKey: ["quantum-config"] });
    },
  });

  const loadDashboardStructure = useMutation({
    mutationFn: ({
      country,
      dashboardId,
    }: {
      country: CountryCode;
      dashboardId: string;
    }) =>
      apiPost<DashboardStructureResponse>(
        `/quantum/countries/${country}/dashboards/${encodeURIComponent(
          dashboardId,
        )}/structure/discover`,
      ),
    onSuccess: async () => {
      const result = await config.refetch();
      if (result.data) setForm(result.data);
      void queryClient.invalidateQueries({ queryKey: ["quantum-config"] });
    },
  });

  const addManualDashboard = useMutation({
    mutationFn: ({
      country,
      payload,
    }: {
      country: CountryCode;
      payload: ManualDashboardPayload;
    }) =>
      apiPost(`/quantum/countries/${country}/dashboards/manual`, {
        url: payload.url,
        name: payload.name,
      }),
    onSuccess: async () => {
      setManualDashboard({ url: "", name: "" });
      setManualDashboardOpen(false);
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
      country: nextCountry,
      countries: [
        ...current.countries,
        emptyCountryConfig(nextCountry, current.countries.length === 0),
      ],
    });
  }

  function selectCountry(country: CountryCode) {
    if (!current) return;
    if (current.countries.some((row) => row.country === country)) {
      setForm({ ...current, country });
      return;
    }
    setForm({
      ...current,
      country,
      countries: [...current.countries, emptyCountryConfig(country)],
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

  function selectDashboard(countryIndex: number, dashboardId: string) {
    if (!current) return;
    const countries = current.countries.map((countryRow, rowIndex) => {
      if (rowIndex !== countryIndex) return countryRow;
      return {
        ...countryRow,
        dashboards: countryRow.dashboards.map((dashboard) => ({
          ...dashboard,
          is_default: dashboard.dashboard_id === dashboardId,
        })),
      };
    });
    setForm({ ...current, countries });
    const row = current.countries[countryIndex];
    if (row && dashboardId) {
      loadDashboardStructure.mutate({ country: row.country, dashboardId });
    }
  }

  function setDefaultDashboard(
    countryIndex: number,
    dashboardIndex: number,
    checked: boolean,
  ) {
    if (!current) return;
    const countries = current.countries.map((countryRow, rowIndex) => {
      if (rowIndex !== countryIndex) return countryRow;
      return {
        ...countryRow,
        dashboards: countryRow.dashboards.map((dashboard, index) => ({
          ...dashboard,
          is_default: checked ? index === dashboardIndex : false,
        })),
      };
    });
    setForm({ ...current, countries });
  }

  function updateWidget(
    countryIndex: number,
    dashboardIndex: number,
    widgetKey: string,
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
                  widgetKeyFor(widget) === widgetKey
                    ? { ...widget, enabled }
                    : widget,
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
    if (!current || !canSaveConfig) return;
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

  function submitManualDashboard() {
    if (!selectedCountry || !manualDashboard.url.trim()) return;
    addManualDashboard.mutate({
      country: selectedCountry.country,
      payload: manualDashboard,
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
                <option value="controlled">
                  Sesion controlada de la aplicacion
                </option>
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
              <span>Profundidad por defecto</span>
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

        <section className="config-panel config-export-panel">
          <div className="section-heading compact">
            <h2 className="heading-with-icon">
              <FolderDown size={18} aria-hidden="true" />
              Ruta de exportaciones
            </h2>
          </div>
          <label className="field config-field-card">
            <FolderDown size={18} aria-hidden="true" />
            <span>Descargas</span>
            <input
              value={current.export_path}
              placeholder="~/Downloads"
              onChange={(event) => update("export_path", event.target.value)}
            />
            <small>Se usa solo al exportar.</small>
          </label>
        </section>

        <section className="config-panel config-country-panel">
          <div className="section-heading compact">
            <h2 className="heading-with-icon">
              <Globe2 size={18} aria-hidden="true" />
              Pais seleccionado
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

          {selectedCountry ? (
            <div className="config-country-focus">
              <label className="field config-field-card">
                <Globe2 size={18} aria-hidden="true" />
                <span>Pais</span>
                <select
                  value={selectedCountry.country}
                  aria-label="Pais seleccionado"
                  onChange={(event) =>
                    selectCountry(event.target.value as CountryCode)
                  }
                >
                  {COUNTRY_OPTIONS.map((option) => (
                    <option key={option.code} value={option.code}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field config-field-card config-url-field">
                <Globe2 size={18} aria-hidden="true" />
                <span>Base URL</span>
                <input
                  value={selectedCountry.base_url}
                  aria-label={`Base URL ${selectedCountry.country}`}
                  onChange={(event) =>
                    updateCountryRow(selectedCountryIndex, {
                      base_url: event.target.value,
                    })
                  }
                />
              </label>
              <div className="config-field-card config-country-state">
                <span className="eyebrow">Default global</span>
                <label className="config-default-toggle">
                  <input
                    type="checkbox"
                    checked={selectedCountry.country === current.country}
                    aria-label={`Default ${selectedCountry.country}`}
                    onChange={(event) =>
                      event.target.checked
                        ? update("country", selectedCountry.country)
                        : undefined
                    }
                  />
                  <span>{countryLabel(selectedCountry.country)}</span>
                </label>
                <span
                  className={`status ${
                    selectedDashboard?.validated ? "ok" : "ko"
                  }`}
                >
                  {selectedDashboard?.validated ? "Validado" : "Pendiente"}
                </span>
              </div>
              <div className="config-row-actions config-country-actions">
                <button
                  className="command-button"
                  type="button"
                  disabled={!selectedCountry.base_url || testCountry.isPending}
                  onClick={() => testCountry.mutate(selectedCountry.country)}
                >
                  <CheckCircle2 size={16} /> Test pais
                </button>
                <button
                  className="command-button"
                  type="button"
                  disabled={
                    !selectedCountry.base_url || refreshDashboards.isPending
                  }
                  onClick={() =>
                    refreshDashboards.mutate(selectedCountry.country)
                  }
                >
                  <RefreshCw size={16} /> Actualizar dashboards
                </button>
                <button
                  className="icon-button danger"
                  type="button"
                  aria-label={`Eliminar ${selectedCountry.country}`}
                  title={`Eliminar ${selectedCountry.country}`}
                  onClick={() => removeCountry(selectedCountryIndex)}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ) : (
            <div className="empty compact">Sin paises configurados</div>
          )}
        </section>

        <section className="config-panel dashboard-config-panel">
          <div className="section-heading compact">
            <h2 className="heading-with-icon">
              <LayoutDashboard size={18} aria-hidden="true" />
              Dashboard default del pais
            </h2>
            {selectedCountry ? (
              <button
                className="command-button"
                type="button"
                onClick={() => setManualDashboardOpen(true)}
              >
                <Plus size={16} /> Anadir dashboard manual
              </button>
            ) : null}
          </div>
          {selectedCountry ? (
            <div className="dashboard-config-list">
              <label className="field dashboard-selector-field">
                <span>Dashboard</span>
                <select
                  value={selectedDashboard?.dashboard_id ?? ""}
                  aria-label={`Dashboard ${selectedCountry.country}`}
                  onChange={(event) =>
                    selectDashboard(selectedCountryIndex, event.target.value)
                  }
                >
                  <option value="" disabled>
                    Selecciona un dashboard
                  </option>
                  {selectedCountry.dashboards.map((dashboard) => (
                    <option
                      key={dashboard.dashboard_id}
                      value={dashboard.dashboard_id}
                    >
                      {dashboardLabel(dashboard)}
                    </option>
                  ))}
                </select>
              </label>

              {manualDashboardOpen ? (
                <section className="manual-dashboard-panel">
                  <header>
                    <h3>Dashboard manual</h3>
                    <button
                      className="icon-button subtle"
                      type="button"
                      aria-label="Cerrar dashboard manual"
                      onClick={() => setManualDashboardOpen(false)}
                    >
                      <X size={16} />
                    </button>
                  </header>
                  <div className="manual-dashboard-grid">
                    <label className="field">
                      <span>URL o dashboard ID</span>
                      <input
                        value={manualDashboard.url}
                        onChange={(event) =>
                          setManualDashboard({
                            ...manualDashboard,
                            url: event.target.value,
                          })
                        }
                      />
                    </label>
                    <label className="field">
                      <span>Nombre visible</span>
                      <input
                        value={manualDashboard.name}
                        placeholder="SDS"
                        onChange={(event) =>
                          setManualDashboard({
                            ...manualDashboard,
                            name: event.target.value,
                          })
                        }
                      />
                    </label>
                  </div>
                  <button
                    className="command-button"
                    type="button"
                    disabled={
                      !manualDashboard.url.trim() ||
                      addManualDashboard.isPending
                    }
                    onClick={submitManualDashboard}
                  >
                    <CheckCircle2 size={16} /> Validar dashboard
                  </button>
                </section>
              ) : null}

              {selectedDashboard ? (
                <section className="dashboard-config-card">
                  <div className="dashboard-config-card-header">
                    <div>
                      <span className="eyebrow">
                        {sourceLabel(selectedDashboard.source)}
                      </span>
                      <h3>{dashboardLabel(selectedDashboard)}</h3>
                    </div>
                    <span
                      className={`status ${
                        selectedDashboard.validated ? "ok" : "ko"
                      }`}
                    >
                      {selectedDashboard.validated ? "Validado" : "Pendiente"}
                    </span>
                  </div>
                  <div className="dashboard-fields-grid">
                    <label className="field">
                      <span>Dashboard ID</span>
                      <input value={selectedDashboard.dashboard_id} readOnly />
                    </label>
                    <label className="field">
                      <span>Nombre</span>
                      <input
                        value={dashboardLabel(selectedDashboard)}
                        readOnly
                      />
                    </label>
                    <label className="field">
                      <span>Tipo</span>
                      <input
                        value={selectedDashboard.dashboard_type}
                        readOnly
                      />
                    </label>
                    <label className="field">
                      <span>Starred</span>
                      <input value="No" readOnly />
                    </label>
                    <label className="field">
                      <span>Team ID</span>
                      <input value={selectedDashboard.team_id} readOnly />
                    </label>
                  </div>
                  <div className="config-row-actions dashboard-actions-row">
                    <label className="config-default-toggle">
                      <input
                        type="checkbox"
                        checked={selectedDashboard.is_default}
                        onChange={(event) =>
                          setDefaultDashboard(
                            selectedCountryIndex,
                            selectedDashboardIndex,
                            event.target.checked,
                          )
                        }
                      />
                      <span>Default del pais</span>
                    </label>
                    <button
                      className="command-button"
                      type="button"
                      disabled={
                        !selectedDashboard.dashboard_id ||
                        loadDashboardStructure.isPending
                      }
                      onClick={() =>
                        loadDashboardStructure.mutate({
                          country: selectedCountry.country,
                          dashboardId: selectedDashboard.dashboard_id,
                        })
                      }
                    >
                      <RefreshCw size={16} /> Actualizar widgets
                    </button>
                  </div>
                  <WidgetGroups
                    dashboard={selectedDashboard}
                    countryIndex={selectedCountryIndex}
                    dashboardIndex={selectedDashboardIndex}
                    onToggle={updateWidget}
                  />
                </section>
              ) : (
                <div className="empty compact">
                  Actualiza dashboards para seleccionar el default del pais.
                </div>
              )}
            </div>
          ) : (
            <div className="empty compact">Sin pais seleccionado</div>
          )}
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
          {countriesMissingDefault.length ? (
            <span className="status ko">
              Selecciona un dashboard default para{" "}
              {countriesMissingDefault.map((row) => row.country).join(", ")}
            </span>
          ) : null}
          <button
            className="button"
            type="submit"
            disabled={save.isPending || !canSaveConfig}
          >
            <Save size={16} /> Guardar
          </button>
        </div>
      </form>
    </>
  );
}

function WidgetGroups({
  dashboard,
  countryIndex,
  dashboardIndex,
  onToggle,
}: {
  dashboard: QuantumDashboardConfig;
  countryIndex: number;
  dashboardIndex: number;
  onToggle: (
    countryIndex: number,
    dashboardIndex: number,
    widgetKey: string,
    enabled: boolean,
  ) => void;
}) {
  const groups = dashboardWidgetGroups(dashboard);
  if (!groups.length) {
    return <div className="empty compact">Sin widgets descubiertos</div>;
  }
  return (
    <div className="widget-config-section-grid">
      {groups.map((group) => (
        <section
          className="widget-config-group"
          key={`${dashboard.dashboard_id}-${group.tabIndex}-${group.title}`}
        >
          <h4>{group.title}</h4>
          <div className="widget-config-grid">
            {group.widgets.map((widget) => {
              const supported = widget.supported ?? Boolean(widget.role);
              return (
                <label
                  className="widget-config-row"
                  key={`${dashboard.dashboard_id}-${widgetKeyFor(widget)}`}
                >
                  <input
                    type="checkbox"
                    checked={widget.enabled && supported}
                    disabled={!supported}
                    onChange={(event) =>
                      onToggle(
                        countryIndex,
                        dashboardIndex,
                        widgetKeyFor(widget),
                        event.target.checked,
                      )
                    }
                  />
                  <span>
                    <strong>{widget.title}</strong>
                    <small>
                      id:{" "}
                      {widget.widget_id || widget.card_id || widget.role || "-"}
                    </small>
                  </span>
                  <em>
                    {widget.widget_type}
                    {supported ? "" : " · no soportado"}
                  </em>
                </label>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}

function dashboardWidgetGroups(dashboard: QuantumDashboardConfig) {
  const tabs = dashboard.tabs?.length
    ? dashboard.tabs
    : tabsFromWidgets(dashboard.widgets);
  const assigned = new Set<string>();
  const groups = tabs.map((tab) => {
    const widgets = dashboard.widgets.filter((widget) => {
      const matches = widgetBelongsToTab(widget, tab);
      if (matches) assigned.add(widgetKeyFor(widget));
      return matches;
    });
    return {
      title: tab.name || "Sin pestana",
      tabIndex: tab.tab_index,
      widgets,
    };
  });
  const unassigned = dashboard.widgets.filter(
    (widget) => !assigned.has(widgetKeyFor(widget)),
  );
  if (unassigned.length) {
    groups.push({
      title: "Sin pestana",
      tabIndex: Number.MAX_SAFE_INTEGER,
      widgets: unassigned,
    });
  }
  return groups.filter((group) => group.widgets.length);
}

function widgetBelongsToTab(
  widget: QuantumWidgetConfig,
  tab: QuantumDashboardTabConfig,
) {
  if (widget.tab_id && tab.tab_id) return widget.tab_id === tab.tab_id;
  if (widget.tab_name) return widget.tab_name === tab.name;
  if (widget.tab && tab.normalized_role) {
    return widget.tab === tab.normalized_role;
  }
  return widget.tab_index === tab.tab_index && !widget.tab_name;
}

function tabsFromWidgets(
  widgets: QuantumWidgetConfig[],
): QuantumDashboardTabConfig[] {
  const byKey = new Map<string, QuantumDashboardTabConfig>();
  widgets.forEach((widget) => {
    const tabName = widget.tab_name || widget.tab || "Tab";
    const key = `${widget.tab_index}-${tabName}`;
    if (!byKey.has(key)) {
      byKey.set(key, {
        tab_index: widget.tab_index,
        name: tabName,
        normalized_role: widget.tab,
      });
    }
  });
  return Array.from(byKey.values()).sort(
    (left, right) => left.tab_index - right.tab_index,
  );
}

function widgetKeyFor(widget: QuantumWidgetConfig) {
  return widget.role || widget.widget_id || widget.card_id || widget.title;
}

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

function normalizeDashboards(
  dashboards: QuantumDashboardConfig[] = [],
): QuantumDashboardConfig[] {
  if (!dashboards.length) return dashboards;
  let defaultSeen = false;
  return dashboards.map((dashboard) => {
    const isDefault = dashboard.is_default && !defaultSeen;
    if (isDefault) defaultSeen = true;
    const widgets = dashboard.widgets ?? [];
    return {
      ...dashboard,
      name: isLegacyGeneratedName(dashboard) ? "" : dashboard.name,
      is_default: isDefault,
      tabs: dashboard.tabs?.length ? dashboard.tabs : tabsFromWidgets(widgets),
      widgets,
    };
  });
}

function isLegacyGeneratedName(dashboard: QuantumDashboardConfig) {
  return (
    dashboard.name === ["Dashboard", "default"].join(" ") &&
    Boolean(dashboard.dashboard_id)
  );
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
    session_mode: config.session_mode ?? "controlled",
    country: countries.some((row) => row.country === config.country)
      ? config.country
      : (countries[0]?.country ?? "MX"),
    countries,
    verify_tls: config.verify_tls ?? true,
    ingestion_depth_days: Number.isInteger(config.ingestion_depth_days)
      ? config.ingestion_depth_days
      : 30,
    theme_preference: config.theme_preference ?? "system",
    export_path: config.export_path || "~/Downloads",
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
      name: "",
      dashboard_type: "Quantum dashboard",
      team_id: row.team_id ?? "",
      summary_tab: row.tab ?? 0,
      errors_tab: 1,
      is_default: true,
      is_manual: false,
      validated: true,
      validation_status: "ok",
      source: "config_cache",
      tabs: [],
      widgets: [],
    },
  ];
}

function dashboardLabel(dashboard: QuantumDashboardConfig) {
  return dashboard.name?.trim() || "Dashboard sin nombre";
}

function sourceLabel(source: QuantumDashboardConfig["source"]) {
  if (source === "manual") return "Manual";
  if (source === "quantum_api" || source === "quantum_web")
    return "Quantum API";
  return "Cache";
}
