import { useMutation, useQuery } from "@tanstack/react-query";
import { Database, Download, RefreshCcw, Trash2, Upload } from "lucide-react";
import { ChangeEvent, useMemo, useRef, useState } from "react";
import {
  apiDelete,
  apiDownload,
  apiGet,
  apiUpload,
} from "../../shared/api/client";
import { countryLabel } from "../../shared/countries";
import { ConfirmDialog } from "../../shared/components/ConfirmDialog";
import { DataGrid } from "../../shared/components/DataGrid";
import { EntityTabs } from "../../shared/components/EntityTabs";
import { EmptyState } from "../../shared/components/EmptyState";
import { MetricBadge } from "../../shared/components/MetricBadge";
import { StatusPill } from "../../shared/components/StatusPill";

type DatasetKpi = {
  id: string;
  title: string;
  value?: number | null;
  unit: "count" | "seconds" | "percent";
};

type DatasetTopApp = {
  name: string;
  operating_system?: string | null;
  page_views?: number | null;
  sessions?: number | null;
  conversions?: number | null;
};

type DatasetTopError = {
  name: string;
  sessions?: number | null;
  sessions_with_error?: number | null;
  error_session_percent?: number | null;
};

type Dataset = {
  status: "ok" | "empty";
  country: string;
  label: string;
  files: number;
  bytes: number;
  updated_at?: string | null;
  raw_calls: number;
  rows: number;
  cards: number;
  captured_cards?: number;
  mandatory_cards?: number;
  mandatory_cards_captured?: number;
  summary_ready?: boolean;
  errors_ready?: boolean;
  derived_datasets?: number;
  regression_status?: string | null;
  last_ingestion_at?: string | null;
  source_start?: string | null;
  source_end?: string | null;
  kpis: DatasetKpi[];
  top_apps: DatasetTopApp[];
  top_errors: DatasetTopError[];
  reason?: string | null;
};

type DatasetsResponse = {
  datasets: Dataset[];
  data_dir?: string;
  legacy_data_detected?: boolean;
};

type DatasetEntity = {
  id: string;
  label: string;
  rows: number;
  files: number;
  bytes: number;
};

type DatasetEntitiesResponse = {
  country: string;
  entities: DatasetEntity[];
};

type DatasetEntityRowsResponse = {
  country: string;
  entity: string;
  rows: Array<Record<string, unknown>>;
  columns: string[];
  total: number;
};

export function DatasetsPage() {
  const fileInput = useRef<HTMLInputElement | null>(null);
  const [selectedCountry, setSelectedCountry] = useState<string | null>(null);
  const [selectedEntity, setSelectedEntity] = useState("raw_api_calls");
  const [deleteCountry, setDeleteCountry] = useState<string | null>(null);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const datasets = useQuery({
    queryKey: ["datasets"],
    queryFn: () => apiGet<DatasetsResponse>("/datasets"),
  });
  const rows = datasets.data?.datasets ?? [];
  const activeCountry = selectedCountry ?? rows[0]?.country ?? "";
  const entities = useQuery({
    queryKey: ["datasets", activeCountry, "entities"],
    queryFn: () =>
      apiGet<DatasetEntitiesResponse>(`/datasets/${activeCountry}/entities`),
    enabled: Boolean(activeCountry),
  });
  const activeEntity = useMemo(() => {
    const available = entities.data?.entities ?? [];
    if (available.some((entity) => entity.id === selectedEntity))
      return selectedEntity;
    return available[0]?.id ?? selectedEntity;
  }, [entities.data?.entities, selectedEntity]);
  const entityRows = useQuery({
    queryKey: ["datasets", activeCountry, "entity", activeEntity],
    queryFn: () =>
      apiGet<DatasetEntityRowsResponse>(
        `/datasets/${activeCountry}/entities/${activeEntity}?limit=100`,
      ),
    enabled: Boolean(activeCountry && activeEntity),
  });

  const remove = useMutation({
    mutationFn: (country: string) =>
      apiDelete(`/datasets/${country}?confirm=${country}`),
    onSuccess: () => {
      setDeleteCountry(null);
      setDeleteConfirmation("");
      void datasets.refetch();
      void entities.refetch();
    },
  });

  const exportData = useMutation({
    mutationFn: (countries: string[]) =>
      apiDownload("/datasets/export", countries),
    onSuccess: ({ blob, filename }) => {
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(url);
    },
  });

  const importData = useMutation({
    mutationFn: (file: File) => {
      const body = new FormData();
      body.append("file", file);
      return apiUpload("/datasets/import", body);
    },
    onSuccess: () => {
      void datasets.refetch();
      void entities.refetch();
    },
  });

  function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) {
      importData.mutate(file);
    }
  }

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Datasets</h1>
          <p className="page-subtitle">
            Ruta de datos local: {datasets.data?.data_dir ?? "-"}
          </p>
          {datasets.data?.legacy_data_detected && (
            <p className="warning-text">
              Se ha detectado una carpeta data legacy. Puedes migrarla a la ruta
              persistente.
            </p>
          )}
        </div>
        <div className="command-group">
          <button
            className="command-button"
            type="button"
            onClick={() => void datasets.refetch()}
          >
            <RefreshCcw size={16} /> Actualizar
          </button>
          <input
            ref={fileInput}
            hidden
            type="file"
            accept=".zip,application/zip"
            onChange={handleFile}
          />
          <button
            className="command-button"
            type="button"
            disabled={importData.isPending}
            onClick={() => fileInput.current?.click()}
          >
            <Upload size={16} /> Importar
          </button>
        </div>
      </header>

      {rows.length ? (
        <section className="dataset-grid">
          {rows.map((dataset) => (
            <article className="dataset-card" key={dataset.country}>
              <header className="dataset-card-header">
                <div>
                  <span className="eyebrow">{dataset.country}</span>
                  <h2>{dataset.label || countryLabel(dataset.country)}</h2>
                  <p>{formatDate(dataset.updated_at)}</p>
                </div>
                <div className="command-group">
                  <button
                    className="icon-button"
                    type="button"
                    aria-label={`Ver entidades ${dataset.country}`}
                    title={`Ver entidades ${dataset.country}`}
                    onClick={() => setSelectedCountry(dataset.country)}
                  >
                    <Database size={16} />
                  </button>
                  <button
                    className="icon-button"
                    type="button"
                    aria-label={`Exportar ${dataset.country}`}
                    title={`Exportar ${dataset.country}`}
                    onClick={() => exportData.mutate([dataset.country])}
                  >
                    <Download size={16} />
                  </button>
                  <button
                    className="icon-button danger"
                    type="button"
                    aria-label={`Eliminar ${dataset.country}`}
                    title={`Eliminar ${dataset.country}`}
                    onClick={() => {
                      setDeleteCountry(dataset.country);
                      setDeleteConfirmation("");
                    }}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </header>

              <div className="dataset-facts">
                <MetricBadge
                  label="RAW calls"
                  value={formatNumber(dataset.raw_calls)}
                />
                <MetricBadge
                  label="Filas RAW"
                  value={formatNumber(dataset.rows)}
                />
                <MetricBadge
                  label="Cards"
                  value={formatNumber(dataset.cards)}
                />
                <StatusPill status={dataset.regression_status} />
                <MetricBadge
                  label="Tamano"
                  value={formatBytes(dataset.bytes)}
                />
              </div>
              <div className="dataset-facts compact">
                <span>
                  obligatorias {formatNumber(dataset.mandatory_cards_captured)}/
                  {formatNumber(dataset.mandatory_cards)}
                </span>
                <span>
                  resumen {dataset.summary_ready ? "ready" : "pendiente"}
                </span>
                <span>
                  errores {dataset.errors_ready ? "ready" : "pendiente"}
                </span>
                <span>derivados {formatNumber(dataset.derived_datasets)}</span>
              </div>
              {dataset.source_start && dataset.source_end && (
                <div className="dataset-range">
                  {formatDate(dataset.source_start)} -{" "}
                  {formatDate(dataset.source_end)}
                </div>
              )}

              {dataset.kpis.length ? (
                <div className="dataset-kpi-grid">
                  {dataset.kpis.map((kpi) => (
                    <div className="dataset-kpi" key={kpi.id}>
                      <span>{kpi.title}</span>
                      <strong>{formatMetric(kpi.value, kpi.unit)}</strong>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="analytics-empty compact">
                  <strong>
                    {dataset.reason ??
                      "Datos raw disponibles, pero no existe dataset analitico derivado."}
                  </strong>
                </div>
              )}

              <div className="dataset-business-grid">
                <section className="business-table">
                  <div className="section-heading compact">
                    <h3>Apps principales</h3>
                  </div>
                  {dataset.top_apps.length ? (
                    <table className="table">
                      <thead>
                        <tr>
                          <th>App</th>
                          <th>SO</th>
                          <th>Sesiones</th>
                          <th>Vistas</th>
                          <th>Conversiones</th>
                        </tr>
                      </thead>
                      <tbody>
                        {dataset.top_apps.map((row) => (
                          <tr key={`${row.name}-${row.operating_system ?? ""}`}>
                            <td>{row.name}</td>
                            <td>{row.operating_system ?? "-"}</td>
                            <td>{formatNumber(row.sessions)}</td>
                            <td>{formatNumber(row.page_views)}</td>
                            <td>{formatNumber(row.conversions)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div className="empty compact">Sin detalle de apps</div>
                  )}
                </section>

                <section className="business-table">
                  <div className="section-heading compact">
                    <h3>Errores principales</h3>
                  </div>
                  {dataset.top_errors.length ? (
                    <table className="table">
                      <thead>
                        <tr>
                          <th>App</th>
                          <th>Sesiones</th>
                          <th>Con error</th>
                          <th>% Error</th>
                        </tr>
                      </thead>
                      <tbody>
                        {dataset.top_errors.map((row) => (
                          <tr key={row.name}>
                            <td>{row.name}</td>
                            <td>{formatNumber(row.sessions)}</td>
                            <td>{formatNumber(row.sessions_with_error)}</td>
                            <td>{formatPercent(row.error_session_percent)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div className="empty compact">Sin detalle de errores</div>
                  )}
                </section>
              </div>
            </article>
          ))}
        </section>
      ) : (
        <div className="empty">Sin datos ingestados</div>
      )}

      {activeCountry && (
        <section className="dataset-card section-offset">
          <div className="section-heading">
            <div>
              <h2>Auditoria Parquet {activeCountry}</h2>
              <span>{entityRows.data?.total ?? 0} filas</span>
            </div>
          </div>
          {entities.data?.entities.length ? (
            <>
              <EntityTabs
                tabs={entities.data.entities.map((entity) => ({
                  id: entity.id,
                  label: entity.id,
                  rows: entity.rows,
                }))}
                active={activeEntity}
                onChange={setSelectedEntity}
              />
              <DataGrid
                columns={entityRows.data?.columns ?? []}
                rows={entityRows.data?.rows ?? []}
              />
            </>
          ) : (
            <EmptyState title="Sin entidades Parquet" />
          )}
        </section>
      )}

      <ConfirmDialog
        open={Boolean(deleteCountry)}
        title="Borrar dataset local"
        message={`Se eliminaran datos RAW, derivados, contratos, regresiones e historico de ingestas de ${countryLabel(deleteCountry ?? "")}. Escribe ${deleteCountry ?? ""} para confirmar.`}
        confirmLabel="Borrar"
        confirmationValue={deleteCountry ?? undefined}
        confirmationInput={deleteConfirmation}
        onConfirmationInput={setDeleteConfirmation}
        onCancel={() => setDeleteCountry(null)}
        onConfirm={() => deleteCountry && remove.mutate(deleteCountry)}
      />
    </>
  );
}

function formatNumber(value?: number | null) {
  return value == null ? "-" : value.toLocaleString();
}

function formatPercent(value?: number | null) {
  return value == null ? "-" : `${value.toLocaleString()}%`;
}

function formatMetric(
  value: number | null | undefined,
  unit: DatasetKpi["unit"],
) {
  if (value == null) return "-";
  if (unit === "seconds") return `${value.toLocaleString()} s`;
  if (unit === "percent") return formatPercent(value);
  return value.toLocaleString();
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  const numeric = Number(value);
  const date = /^\d+$/.test(value)
    ? new Date(numeric > 10_000_000_000 ? numeric : numeric * 1000)
    : new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("es", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}
