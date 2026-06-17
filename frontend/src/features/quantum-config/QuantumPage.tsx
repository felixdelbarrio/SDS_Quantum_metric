import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Palette, Plus, Save, Trash2 } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { apiGet, apiPut } from "../../shared/api/client";
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
  const activeCountryExists = countryRows.some(
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
      countries: [...current.countries, emptyCountryConfig(nextCountry)],
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
      country: activeCountryExists
        ? current.country
        : (current.countries[0]?.country ?? current.country),
      manual_cookie:
        current.session_mode === "manual" ? manualCookie : undefined,
    });
  }

  if (!current) return <div className="empty">Cargando</div>;

  return (
    <>
      <header className="page-header">
        <h1>Quantum</h1>
      </header>

      <form className="config-surface" onSubmit={onSubmit}>
        <section className="config-panel">
          <div className="toolbar">
            <label className="field">
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
            <label className="field">
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
            <label className="field">
              <span>Pais activo</span>
              <select
                value={current.country}
                disabled={!countryRows.length}
                onChange={(event) =>
                  update("country", event.target.value as CountryCode)
                }
              >
                {countryRows.map((row) => (
                  <option key={row.country} value={row.country}>
                    {countryLabel(row.country)}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </section>

        <section className="config-panel">
          <div className="section-heading compact">
            <h2 className="heading-with-icon">
              <Palette size={18} aria-hidden="true" />
              Apariencia
            </h2>
          </div>
          <label className="field theme-select">
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
        </section>

        <section className="config-panel">
          <label className="field">
            <span>Profundidad de datos a ingestar</span>
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
        </section>

        <section className="config-panel">
          <div className="section-heading compact">
            <h2>Paises Quantum</h2>
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
            <div className="table-scroll">
              <table className="table config-table">
                <thead>
                  <tr>
                    <th>Pais</th>
                    <th>Base URL</th>
                    <th>Activo</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {countryRows.map((row, index) => (
                    <tr key={`${row.country}-${index}`}>
                      <td>
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
                      </td>
                      <td>
                        <input
                          value={row.base_url}
                          aria-label={`Base URL ${row.country}`}
                          onChange={(event) =>
                            updateCountryRow(index, {
                              base_url: event.target.value,
                            })
                          }
                        />
                      </td>
                      <td>
                        <input
                          type="checkbox"
                          checked={row.enabled}
                          aria-label={`Activo ${row.country}`}
                          onChange={(event) =>
                            updateCountryRow(index, {
                              enabled: event.target.checked,
                            })
                          }
                        />
                      </td>
                      <td>
                        <button
                          className="icon-button danger"
                          type="button"
                          aria-label={`Eliminar ${row.country}`}
                          title={`Eliminar ${row.country}`}
                          onClick={() => removeCountry(index)}
                        >
                          <Trash2 size={16} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty compact">Sin paises configurados</div>
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

function emptyCountryConfig(country: CountryCode): QuantumCountryConfig {
  return {
    country,
    base_url: "",
    enabled: true,
    dashboard_resolved: false,
  };
}
