import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Database,
  Globe2,
  Monitor,
  Palette,
  Plus,
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
  dashboard_resolved?: boolean;
};

type QuantumConfig = {
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
    queryFn: () => apiGet<QuantumConfig>("/config/quantum"),
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
      apiPost(`/quantum/test-connection?country=${country}`),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["quantum-config"] }),
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
        enabled: row.country === current.country,
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
                    <span
                      className={`status ${row.dashboard_resolved ? "ok" : ""}`}
                    >
                      {row.dashboard_resolved ? "Dashboard" : "Pendiente"}
                    </span>
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

        <section className="config-panel">
          <div className="section-heading compact">
            <h2 className="heading-with-icon">
              <Database size={18} aria-hidden="true" />
              Dashboards y widgets
            </h2>
          </div>
          <div className="dashboard-config-list">
            {countryRows.map((row) => (
              <article className="dashboard-config-item" key={row.country}>
                <header>
                  <div>
                    <span className="eyebrow">Preview operativo</span>
                    <strong>{countryLabel(row.country)}</strong>
                  </div>
                  <span
                    className={`status ${row.dashboard_resolved ? "ok" : ""}`}
                  >
                    {row.dashboard_resolved
                      ? "Dashboard default resuelto"
                      : "Test pais pendiente"}
                  </span>
                </header>
                <div className="widget-config-section-grid">
                  {WIDGET_CONFIG_GROUPS.map((group) => (
                    <section
                      className="widget-config-group"
                      key={`${row.country}-${group.title}`}
                    >
                      <h3>{group.title}</h3>
                      <div className="widget-config-grid">
                        {group.widgets.map((widget) => (
                          <label key={`${row.country}-${widget.id}`}>
                            <input type="checkbox" checked readOnly />
                            <span>{widget.title}</span>
                          </label>
                        ))}
                      </div>
                    </section>
                  ))}
                </div>
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
    widgets: [
      { id: "summary.page_views", title: "Paginas vistas" },
      { id: "summary.sessions", title: "Sesiones" },
      { id: "summary.converted_sessions", title: "Sesiones con conversion" },
      { id: "summary.avg_session_duration", title: "Tiempo medio de sesion" },
      { id: "summary.detail_by_app_name_os", title: "Detalle App Name / SO" },
    ],
  },
  {
    title: "Errores",
    widgets: [
      {
        id: "errors.error_sessions_percentage_evolution",
        title: "% sesiones con error",
      },
      { id: "errors.top_errors_by_error_name", title: "Top errores" },
      {
        id: "errors.error_sessions_by_app_name_comparison",
        title: "Comparativa App Name",
      },
      {
        id: "errors.error_session_percentage_by_app_name",
        title: "% error por App Name",
      },
    ],
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
  };
}
