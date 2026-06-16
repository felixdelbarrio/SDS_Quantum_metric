import { useMutation, useQuery } from "@tanstack/react-query";
import { Play, RefreshCcw, Square } from "lucide-react";
import { FormEvent, useEffect, useMemo } from "react";
import { apiGet, apiPost } from "../../shared/api/client";
import { CountryCode, countryLabel } from "../../shared/countries";
import { useAppStore } from "../../shared/state/appStore";

type IngestionJob = {
  ingestion_id: string;
  country: string;
  status:
    | "pending"
    | "running"
    | "planning_range"
    | "capturing_day"
    | "capturing_required_cards"
    | "capturing_web"
    | "capturing_summary_tab"
    | "capturing_errors_tab"
    | "persisting_raw"
    | "building_derived"
    | "building_contracts"
    | "building_derived_datasets"
    | "running_regression"
    | "completed"
    | "completed_with_warnings"
    | "failed"
    | "failed_regression"
    | "cancelled";
  started_at: string;
  finished_at?: string;
  endpoint_current?: string;
  records_received: number;
  records_persisted: number;
  pages_processed: number;
  errors: string[];
  duration_seconds?: number;
  details: Record<string, unknown>;
};

type IngestionsResponse = {
  active: IngestionJob[];
  persisted: IngestionJob[];
};

type QuantumCountryConfig = {
  country: CountryCode;
  base_url: string;
  enabled: boolean;
  dashboard_resolved?: boolean;
};

type QuantumConfig = {
  country: CountryCode;
  countries: QuantumCountryConfig[];
};

export function IngestionPage() {
  const { activeCountry, setActiveCountry } = useAppStore();
  const config = useQuery({
    queryKey: ["quantum-config"],
    queryFn: () => apiGet<QuantumConfig>("/config/quantum"),
  });
  const ingestions = useQuery({
    queryKey: ["ingestions"],
    queryFn: () => apiGet<IngestionsResponse>("/ingestions"),
    refetchInterval: 2500,
  });

  const configuredCountries = useMemo(
    () => config.data?.countries.filter((country) => country.enabled) ?? [],
    [config.data?.countries],
  );
  const selectedConfig = configuredCountries.find(
    (country) => country.country === activeCountry,
  );

  const create = useMutation({
    mutationFn: () =>
      apiPost<IngestionJob>("/ingestions", {
        country: activeCountry,
      }),
    onSuccess: () => void ingestions.refetch(),
  });

  const canIngest = Boolean(selectedConfig?.base_url && !create.isPending);

  const cancel = useMutation({
    mutationFn: (id: string) =>
      apiPost<IngestionJob>(`/ingestions/${id}/cancel`),
    onSuccess: () => void ingestions.refetch(),
  });

  useEffect(() => {
    if (!configuredCountries.length) return;
    if (
      !configuredCountries.some((country) => country.country === activeCountry)
    ) {
      setActiveCountry(configuredCountries[0].country);
    }
  }, [activeCountry, configuredCountries, setActiveCountry]);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!canIngest) return;
    create.mutate();
  }

  const jobs = [
    ...(ingestions.data?.active ?? []),
    ...(ingestions.data?.persisted ?? []),
  ];

  return (
    <>
      <header className="page-header">
        <h1>Ingesta</h1>
        <button
          className="command-button"
          onClick={() => void ingestions.refetch()}
        >
          <RefreshCcw size={16} /> Actualizar
        </button>
      </header>

      <form className="card toolbar" onSubmit={onSubmit}>
        <label className="field">
          <span>Pais</span>
          <select
            value={activeCountry}
            disabled={!configuredCountries.length}
            onChange={(event) => setActiveCountry(event.target.value)}
          >
            {configuredCountries.length ? (
              configuredCountries.map((country) => (
                <option key={country.country} value={country.country}>
                  {countryLabel(country.country)}
                </option>
              ))
            ) : (
              <option value={activeCountry}>Sin paises</option>
            )}
          </select>
        </label>
        <button className="button" type="submit" disabled={!canIngest}>
          <Play size={16} /> Ingestar
        </button>
      </form>

      {!configuredCountries.length && (
        <div className="analytics-empty compact section-offset">
          <strong>Sin paises configurados</strong>
        </div>
      )}

      <section className="card section-offset">
        {jobs.length ? (
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Pais</th>
                <th>Estado</th>
                <th>Calls</th>
                <th>Filas</th>
                <th>Cards</th>
                <th>Obligatorias</th>
                <th>Derivados</th>
                <th>Regresion</th>
                <th>Rango</th>
                <th>Duracion</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={`${job.ingestion_id}-${job.status}`}>
                  <td>{job.ingestion_id.slice(0, 8)}</td>
                  <td>{job.country}</td>
                  <td>
                    <span
                      className={`status ${job.status === "completed" ? "ok" : ""}`}
                    >
                      {job.status}
                    </span>
                  </td>
                  <td>{job.records_persisted}</td>
                  <td>{job.records_received}</td>
                  <td>{String(job.details.cards_captured ?? "-")}</td>
                  <td>
                    {String(job.details.mandatory_cards_captured ?? "-")}/
                    {String(job.details.mandatory_cards ?? "-")}
                  </td>
                  <td>{String(job.details.derived_datasets ?? "-")}</td>
                  <td>{String(job.details.regression_status ?? "-")}</td>
                  <td>{formatRange(job.details.range)}</td>
                  <td>{job.duration_seconds ?? "-"}</td>
                  <td>
                    {![
                      "completed",
                      "failed",
                      "failed_regression",
                      "cancelled",
                    ].includes(job.status) && (
                      <button
                        className="button danger"
                        onClick={() => cancel.mutate(job.ingestion_id)}
                      >
                        <Square size={16} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="empty">Sin ingestas</div>
        )}
      </section>
    </>
  );
}

function formatRange(value: unknown) {
  if (!value || typeof value !== "object") return "-";
  const range = value as { start?: string; end?: string; mode?: string };
  return `${range.mode ?? "range"} ${range.start ?? "-"} -> ${range.end ?? "-"}`;
}
