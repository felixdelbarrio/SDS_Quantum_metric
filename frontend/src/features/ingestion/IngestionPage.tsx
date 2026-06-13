import { useMutation, useQuery } from "@tanstack/react-query";
import { Play, RefreshCcw, Square } from "lucide-react";
import { FormEvent } from "react";
import { apiGet, apiPost } from "../../shared/api/client";
import { useAppStore } from "../../shared/state/appStore";

type IngestionJob = {
  ingestion_id: string;
  country: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
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

export function IngestionPage() {
  const { activeCountry, setActiveCountry } = useAppStore();
  const ingestions = useQuery({
    queryKey: ["ingestions"],
    queryFn: () => apiGet<IngestionsResponse>("/ingestions"),
    refetchInterval: 2500,
  });

  const create = useMutation({
    mutationFn: () =>
      apiPost<IngestionJob>("/ingestions", {
        country: activeCountry,
      }),
    onSuccess: () => void ingestions.refetch(),
  });

  const cancel = useMutation({
    mutationFn: (id: string) =>
      apiPost<IngestionJob>(`/ingestions/${id}/cancel`),
    onSuccess: () => void ingestions.refetch(),
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
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
            onChange={(event) => setActiveCountry(event.target.value)}
          >
            <option value="ES">Espana</option>
            <option value="MX">Mexico</option>
            <option value="PE">Peru</option>
            <option value="CO">Colombia</option>
            <option value="AR">Argentina</option>
          </select>
        </label>
        <button className="button" type="submit" disabled={create.isPending}>
          <Play size={16} /> Ingestar
        </button>
      </form>

      <section className="card" style={{ marginTop: 16 }}>
        {jobs.length ? (
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Pais</th>
                <th>Estado</th>
                <th>Calls</th>
                <th>Filas</th>
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
                  <td>{job.duration_seconds ?? "-"}</td>
                  <td>
                    {job.status === "running" && (
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
