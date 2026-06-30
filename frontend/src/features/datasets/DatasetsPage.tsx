import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, Trash2, Upload } from "lucide-react";
import { ChangeEvent, useMemo, useRef, useState } from "react";
import { apiDelete, apiGet, apiPost, apiUpload } from "../../shared/api/client";
import { countryLabel } from "../../shared/countries";
import { ConfirmDialog } from "../../shared/components/ConfirmDialog";
import { DataGrid } from "../../shared/components/DataGrid";
import { EntityTabs } from "../../shared/components/EntityTabs";
import { EmptyState } from "../../shared/components/EmptyState";
import { MetricBadge } from "../../shared/components/MetricBadge";
import { StatusPill } from "../../shared/components/StatusPill";

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
  category?: string | null;
  dashboard_id?: string | null;
  dashboard_name?: string | null;
  widget_id?: string | null;
  widget_role?: string | null;
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

type ExportResponse = {
  status: "exported" | "empty";
  path?: string;
  filename?: string;
  size_bytes?: number;
};

export function DatasetsPage() {
  const fileInput = useRef<HTMLInputElement | null>(null);
  const [selectedCountry, setSelectedCountry] = useState<string | null>(null);
  const [selectedEntity, setSelectedEntity] = useState("raw_api_calls");
  const [deleteCountry, setDeleteCountry] = useState<string | null>(null);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [latestExport, setLatestExport] = useState<ExportResponse | null>(null);
  const datasets = useQuery({
    queryKey: ["datasets"],
    queryFn: () => apiGet<DatasetsResponse>("/datasets"),
  });
  const rows = datasets.data?.datasets ?? [];
  const datasetsInitialLoading = datasets.isLoading && !datasets.data;
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
  const entityGroups = useMemo(() => {
    const grouped = new Map<string, DatasetEntity[]>();
    for (const entity of entities.data?.entities ?? []) {
      const key = entity.category ?? "Entidad";
      const dashboardLabel = entity.dashboard_name ?? entity.dashboard_id;
      const groupKey = dashboardLabel ? `${dashboardLabel} · ${key}` : key;
      grouped.set(groupKey, [...(grouped.get(groupKey) ?? []), entity]);
    }
    return Array.from(grouped.entries());
  }, [entities.data?.entities]);

  const remove = useMutation({
    mutationFn: (country: string) =>
      apiDelete(`/datasets/${country}?confirm=${country}`),
    onSuccess: () => {
      setDeleteCountry(null);
      setDeleteConfirmation("");
      void datasets.refetch();
    },
  });

  const exportData = useMutation({
    mutationFn: (countries: string[]) =>
      apiPost<ExportResponse>("/datasets/export", { countries }),
    onSuccess: (result) => {
      setLatestExport(result);
    },
  });

  const importData = useMutation({
    mutationFn: (file: File) => {
      const body = new FormData();
      body.append("file", file);
      return apiUpload("/datasets/import", body);
    },
    onSuccess: () => void datasets.refetch(),
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

      {datasetsInitialLoading ? (
        <div className="analytics-loading" role="status">
          Cargando datasets
        </div>
      ) : datasets.isError ? (
        <EmptyState title="No se pudieron cargar los datasets" />
      ) : rows.length ? (
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
                    className="command-button"
                    type="button"
                    onClick={() => setSelectedCountry(dataset.country)}
                  >
                    Entidades
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
            </article>
          ))}
        </section>
      ) : (
        <div className="empty">Sin datos ingestados</div>
      )}

      {latestExport?.status === "exported" && (
        <section className="dataset-card export-result-card">
          <div className="section-heading compact">
            <div>
              <h2>Export creado</h2>
              <span>{latestExport.filename}</span>
            </div>
            <MetricBadge
              label="Tamano"
              value={formatBytes(latestExport.size_bytes ?? 0)}
            />
          </div>
          <p className="page-subtitle">{latestExport.path}</p>
        </section>
      )}

      {activeCountry && (
        <section className="dataset-card section-offset">
          <div className="section-heading">
            <div>
              <h2>Entidades Parquet {activeCountry}</h2>
              <span>{entityRows.data?.total ?? 0} filas</span>
            </div>
            <button
              className="command-button"
              type="button"
              disabled={!entityRows.data?.rows?.length}
              onClick={() =>
                exportEntityCsv(
                  activeCountry,
                  activeEntity,
                  entityRows.data?.columns ?? [],
                  entityRows.data?.rows ?? [],
                )
              }
            >
              <Download size={16} /> CSV
            </button>
          </div>
          {entities.isLoading && !entities.data ? (
            <div className="analytics-loading" role="status">
              Cargando entidades
            </div>
          ) : entities.isError ? (
            <EmptyState title="No se pudieron cargar las entidades" />
          ) : entities.data?.entities.length ? (
            <>
              <div className="dataset-entity-groups">
                {entityGroups.map(([category, items]) => (
                  <section className="dataset-entity-group" key={category}>
                    <h3>{category}</h3>
                    <div>
                      {items.slice(0, 6).map((entity) => (
                        <button
                          type="button"
                          key={entity.id}
                          className={
                            entity.id === activeEntity
                              ? "entity-chip active"
                              : "entity-chip"
                          }
                          onClick={() => setSelectedEntity(entity.id)}
                        >
                          <span>{entity.id}</span>
                          <small>
                            {entity.widget_id ?? entity.widget_role ?? "config"}
                          </small>
                        </button>
                      ))}
                    </div>
                  </section>
                ))}
              </div>
              <EntityTabs
                tabs={entities.data.entities.map((entity) => ({
                  id: entity.id,
                  label: entity.id,
                  rows: entity.rows,
                }))}
                active={activeEntity}
                onChange={setSelectedEntity}
              />
              {entityRows.isLoading && !entityRows.data ? (
                <div className="analytics-loading" role="status">
                  Cargando filas
                </div>
              ) : (
                <DataGrid
                  columns={entityRows.data?.columns ?? []}
                  rows={entityRows.data?.rows ?? []}
                />
              )}
            </>
          ) : (
            <EmptyState title="Sin entidades Parquet" />
          )}
        </section>
      )}

      <ConfirmDialog
        open={Boolean(deleteCountry)}
        title="Borrar dataset local"
        message={`Escribe ${deleteCountry ?? ""} para borrar RAW, derivados y regresion.`}
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

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function exportEntityCsv(
  country: string,
  entity: string,
  columns: string[],
  rows: Array<Record<string, unknown>>,
) {
  const body = rows.map((row) =>
    columns.map((column) => csvCell(row[column])).join(","),
  );
  const blob = new Blob([[columns.join(","), ...body].join("\n")], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${country}-${entity.replaceAll("/", "-")}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function csvCell(value: unknown) {
  if (value === null || value === undefined) return "";
  const text =
    typeof value === "object" ? JSON.stringify(value) : String(value);
  return `"${text.replaceAll('"', '""')}"`;
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
