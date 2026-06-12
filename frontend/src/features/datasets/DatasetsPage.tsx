import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, RefreshCcw, Trash2, Upload } from "lucide-react";
import { ChangeEvent, useRef } from "react";
import {
  apiDelete,
  apiDownload,
  apiGet,
  apiUpload,
} from "../../shared/api/client";

type Dataset = {
  country: string;
  files: number;
  bytes: number;
  updated_at?: string;
};

type DatasetsResponse = {
  datasets: Dataset[];
};

export function DatasetsPage() {
  const fileInput = useRef<HTMLInputElement | null>(null);
  const datasets = useQuery({
    queryKey: ["datasets"],
    queryFn: () => apiGet<DatasetsResponse>("/datasets"),
  });

  const remove = useMutation({
    mutationFn: (country: string) => apiDelete(`/datasets/${country}`),
    onSuccess: () => void datasets.refetch(),
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
    onSuccess: () => void datasets.refetch(),
  });

  function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) {
      importData.mutate(file);
    }
  }

  const rows = datasets.data?.datasets ?? [];

  return (
    <>
      <header className="page-header">
        <h1>Datasets</h1>
        <button
          className="button secondary"
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
          className="button secondary"
          disabled={importData.isPending}
          onClick={() => fileInput.current?.click()}
        >
          <Upload size={16} /> Importar
        </button>
      </header>

      <section className="card">
        {rows.length ? (
          <table className="table">
            <thead>
              <tr>
                <th>Pais</th>
                <th>Archivos</th>
                <th>Bytes</th>
                <th>Actualizado</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((dataset) => (
                <tr key={dataset.country}>
                  <td>{dataset.country}</td>
                  <td>{dataset.files}</td>
                  <td>{dataset.bytes.toLocaleString()}</td>
                  <td>{dataset.updated_at ?? "-"}</td>
                  <td className="toolbar">
                    <button
                      className="button secondary"
                      aria-label={`Exportar ${dataset.country}`}
                      title={`Exportar ${dataset.country}`}
                      onClick={() => exportData.mutate([dataset.country])}
                    >
                      <Download size={16} />
                    </button>
                    <button
                      className="button danger"
                      aria-label={`Eliminar ${dataset.country}`}
                      title={`Eliminar ${dataset.country}`}
                      onClick={() => remove.mutate(dataset.country)}
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="empty">Sin Parquet local</div>
        )}
      </section>
    </>
  );
}
