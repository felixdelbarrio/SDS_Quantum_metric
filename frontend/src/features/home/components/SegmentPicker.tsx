import { Search, X } from "lucide-react";
import { useMemo, useState } from "react";
import { DashboardSelection, SegmentsResponse } from "../types";
import { EmptyAnalyticsState } from "./EmptyAnalyticsState";

type Props = {
  open: boolean;
  response?: SegmentsResponse;
  selected?: DashboardSelection | null;
  isLoading: boolean;
  onApply: (segmentId: string) => void;
  onClear: () => void;
  onClose: () => void;
};

export function SegmentPicker({
  open,
  response,
  selected,
  isLoading,
  onApply,
  onClear,
  onClose,
}: Props) {
  const [search, setSearch] = useState("");
  const segments = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    const values = response?.segments ?? [];
    if (!needle) return values;
    return values.filter(
      (segment) =>
        segment.label.toLocaleLowerCase().includes(needle) ||
        segment.id.toLocaleLowerCase().includes(needle),
    );
  }, [response?.segments, search]);

  if (!open) return null;

  return (
    <aside className="side-panel" aria-label="Dashboard Segment">
      <div className="side-panel-header">
        <div>
          <strong>Dashboard Segment</strong>
          <span>{selected?.label ?? "Sin segmento activo"}</span>
        </div>
        <button className="icon-button" onClick={onClose} aria-label="Cerrar">
          <X size={16} />
        </button>
      </div>

      <label className="search-field">
        <Search size={16} aria-hidden="true" />
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Buscar segmentos"
        />
      </label>

      <div className="panel-actions">
        <button className="button secondary" onClick={onClear}>
          Limpiar segmento
        </button>
      </div>

      {isLoading ? (
        <div className="analytics-loading">Cargando segmentos</div>
      ) : segments.length ? (
        <div className="picker-list">
          {segments.map((segment) => (
            <button
              key={segment.id}
              className={selected?.id === segment.id ? "selected" : ""}
              onClick={() => onApply(segment.id)}
            >
              <span>{segment.label}</span>
              <small>{segment.count.toLocaleString()} filas</small>
            </button>
          ))}
        </div>
      ) : (
        <EmptyAnalyticsState
          title="Sin segmentos disponibles"
          reason="No hay valores locales suficientes para construir filtros persistentes."
        />
      )}
    </aside>
  );
}
