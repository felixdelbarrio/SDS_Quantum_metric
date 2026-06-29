import { useMutation, useQuery } from "@tanstack/react-query";
import { Play, Square } from "lucide-react";
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
    | "planning_chunks"
    | "capturing_chunk"
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
  planned_chunks: number;
  completed_chunks: number;
  current_chunk_index?: number | null;
  current_chunk_start?: string | null;
  current_chunk_end?: string | null;
  chunks?: Array<{
    index: number;
    start: string;
    end: string;
    label: string;
    status: string;
    completed_at?: string | null;
  }>;
  mandatory_cards_total: number;
  mandatory_cards_captured: number;
  calls_captured: number;
  rows_captured: number;
  derived_datasets: number;
  regression_status?: string | null;
  progress_percent: number;
  last_progress_at?: string | null;
  message?: string | null;
  errors: string[];
  duration_seconds?: number;
  details: Record<string, unknown>;
};

type IngestionsResponse = {
  active: IngestionJob[];
  history?: IngestionJob[];
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
    () => config.data?.countries ?? [],
    [config.data?.countries],
  );
  const selectedConfig = configuredCountries.find(
    (country) => country.country === activeCountry,
  );

  const create = useMutation({
    mutationFn: () => {
      const today = todayInMexico();
      const start = addDays(today, -6);
      return apiPost<IngestionJob>("/ingestions", {
        country: activeCountry,
        range_key: "last_7_days",
        start_date: start,
        end_date: today,
      });
    },
    onSuccess: () => void ingestions.refetch(),
  });

  const activeJobs = (ingestions.data?.active ?? []).filter(
    (job) => !isTerminalJob(job),
  );
  const activeJob = activeJobs.find((job) => job.country === activeCountry);
  const countryBusy = Boolean(activeJob);
  const canIngest = Boolean(
    selectedConfig?.base_url && !create.isPending && !countryBusy,
  );

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

  const history = mergeHistory(
    ingestions.data?.history ?? ingestions.data?.persisted ?? [],
    ingestions.data?.active ?? [],
  );

  return (
    <>
      <header className="page-header">
        <h1>Ingesta</h1>
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
          <Play size={16} /> {countryBusy ? "Ingesta en curso" : "Ingestar"}
        </button>
      </form>

      {!configuredCountries.length && (
        <div className="analytics-empty compact section-offset">
          <strong>Sin paises configurados</strong>
        </div>
      )}

      {activeJob ? (
        <section className="card section-offset">
          <div className="section-heading">
            <div>
              <h2>Ingesta en curso</h2>
              <span>{countryLabel(activeJob.country as CountryCode)}</span>
            </div>
          </div>
          <IngestionCard job={activeJob} onCancel={cancel.mutate} />
        </section>
      ) : null}

      <section className="card section-offset">
        <div className="section-heading">
          <div>
            <h2>Historico de ingestas</h2>
            <span>{history.length} ejecuciones</span>
          </div>
        </div>
        {history.length ? (
          <IngestionHistoryTable jobs={history} />
        ) : (
          <div className="empty">Sin ingestas</div>
        )}
      </section>
    </>
  );
}

function IngestionCard({
  job,
  onCancel,
}: {
  job: IngestionJob;
  onCancel: (id: string) => void;
}) {
  const chunks = [...(job.chunks ?? [])].sort(
    (left, right) => left.index - right.index,
  );
  const isTerminal = [
    "completed",
    "failed",
    "failed_regression",
    "cancelled",
  ].includes(job.status);
  return (
    <article className="ingestion-progress-card">
      <header>
        <div>
          <strong>{job.ingestion_id.slice(0, 8)}</strong>
          <span>{job.country}</span>
        </div>
        <span className={`status ${job.status === "completed" ? "ok" : ""}`}>
          {job.status}
        </span>
      </header>
      <progress
        className="progress-meter"
        aria-label="Progreso de ingesta"
        value={Math.max(0, Math.min(100, job.progress_percent ?? 0))}
        max={100}
      />
      <div className="dataset-facts compact">
        <span>
          {job.completed_chunks}/{job.planned_chunks} chunks
        </span>
        <span>{job.calls_captured || job.records_persisted} calls</span>
        <span>{job.rows_captured || job.records_received} filas</span>
        <span>
          {job.mandatory_cards_captured}/{job.mandatory_cards_total}{" "}
          obligatorias
        </span>
        <span>
          {job.derived_datasets || String(job.details.derived_datasets ?? "-")}{" "}
          derivados
        </span>
        <span>
          {job.regression_status ??
            String(job.details.regression_status ?? "-")}
        </span>
      </div>
      <p className="page-subtitle">
        {job.message ?? formatRange(job.details.range)}
      </p>
      <p className="page-subtitle">
        Chunk actual: {job.current_chunk_index ?? "-"} ·{" "}
        {job.current_chunk_start ?? "-"} - {job.current_chunk_end ?? "-"}
      </p>
      <p className="page-subtitle">
        Actualizado: {formatDate(job.last_progress_at)} · Duracion:{" "}
        {job.duration_seconds ?? "-"}
      </p>
      {!!chunks.length && (
        <ol className="ingestion-chunks">
          {chunks.map((chunk) => (
            <li key={chunk.index}>
              <span>{chunk.index}</span>
              <strong>{chunk.label}</strong>
              <em>{chunk.status}</em>
            </li>
          ))}
        </ol>
      )}
      {!!job.errors.length && (
        <p className="warning-text">{job.errors.join(" · ")}</p>
      )}
      {!isTerminal && (
        <button
          className="button danger"
          onClick={() => onCancel(job.ingestion_id)}
        >
          <Square size={16} /> Cancelar
        </button>
      )}
    </article>
  );
}

function IngestionHistoryTable({ jobs }: { jobs: IngestionJob[] }) {
  return (
    <div className="table-scroll">
      <table className="table dashboard-table ingestion-history-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Pais</th>
            <th>Estado</th>
            <th>Inicio</th>
            <th>Fin</th>
            <th>Resultado</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.ingestion_id}>
              <td>{job.ingestion_id.slice(0, 8)}</td>
              <td>{job.country}</td>
              <td>{job.status}</td>
              <td>{formatDate(job.started_at)}</td>
              <td>{formatDate(job.finished_at)}</td>
              <td title={ingestionResult(job)}>{ingestionResult(job)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function mergeHistory(history: IngestionJob[], active: IngestionJob[]) {
  const byId = new Map<string, IngestionJob>();
  [...history, ...active.filter(isTerminalJob)].forEach((job) => {
    byId.set(job.ingestion_id, job);
  });
  return [...byId.values()].sort(
    (left, right) =>
      new Date(right.started_at).valueOf() -
      new Date(left.started_at).valueOf(),
  );
}

function isTerminalJob(job: IngestionJob) {
  return ["completed", "failed", "failed_regression", "cancelled"].includes(
    job.status,
  );
}

function ingestionResult(job: IngestionJob) {
  const regression =
    job.regression_status ?? String(job.details?.regression_status ?? "");
  if (regression) return regression;
  const failure = String(job.details?.failure ?? job.errors[0] ?? "");
  if (!failure) return "-";
  return failure.length > 120 ? `${failure.slice(0, 117)}...` : failure;
}

function todayInMexico() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Mexico_City",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const value = Object.fromEntries(
    parts.map((part) => [part.type, part.value]),
  );
  return `${value.year}-${value.month}-${value.day}`;
}

function addDays(value: string, days: number) {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("es", {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(date);
}

function formatRange(value: unknown) {
  if (!value || typeof value !== "object") return "-";
  const range = value as { start?: string; end?: string; mode?: string };
  return `${range.mode ?? "range"} ${range.start ?? "-"} -> ${range.end ?? "-"}`;
}
