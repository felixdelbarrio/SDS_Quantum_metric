import { Search, X } from "lucide-react";
import { useMemo, useState } from "react";
import {
  DashboardDimensionGroup,
  DashboardSelection,
  DimensionsResponse,
} from "../types";
import { EmptyAnalyticsState } from "./EmptyAnalyticsState";

type Props = {
  open: boolean;
  response?: DimensionsResponse;
  selected?: DashboardSelection | null;
  isLoading: boolean;
  onApply: (dimensionId: string) => void;
  onClear: () => void;
  onClose: () => void;
};

export function DimensionPicker({
  open,
  response,
  selected,
  isLoading,
  onApply,
  onClear,
  onClose,
}: Props) {
  const [search, setSearch] = useState("");
  const groups = useMemo(
    () => filterGroups(response?.groups ?? [], search),
    [response?.groups, search],
  );

  if (!open) return null;

  return (
    <aside className="side-panel" aria-label="Add Dashboard Dimension">
      <div className="side-panel-header">
        <div>
          <strong>Add Dashboard Dimension</strong>
          <span>{selected?.label ?? "Sin dimension activa"}</span>
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
          placeholder="Buscar dimensiones"
        />
      </label>

      <div className="panel-actions">
        <button className="button secondary" onClick={onClear}>
          Quitar dimension
        </button>
      </div>

      {isLoading ? (
        <div className="analytics-loading">Cargando dimensiones</div>
      ) : groups.length ? (
        <div className="dimension-groups">
          {groups.map((group) => (
            <details key={group.label} open>
              <summary>{group.label}</summary>
              <div className="picker-list">
                {group.items.map((item) => (
                  <button
                    key={item.id}
                    className={selected?.id === item.id ? "selected" : ""}
                    onClick={() => onApply(item.id)}
                  >
                    <span>{item.label}</span>
                    {item.status === "insufficient_data" && (
                      <small>datos insuficientes</small>
                    )}
                  </button>
                ))}
              </div>
            </details>
          ))}
        </div>
      ) : (
        <EmptyAnalyticsState
          title="Sin dimensiones disponibles"
          reason="No se han inferido dimensiones desde request_json ni response_json."
        />
      )}
    </aside>
  );
}

function filterGroups(groups: DashboardDimensionGroup[], search: string) {
  const needle = search.trim().toLocaleLowerCase();
  if (!needle) return groups;
  return groups
    .map((group) => ({
      ...group,
      items: group.items.filter(
        (item) =>
          item.label.toLocaleLowerCase().includes(needle) ||
          item.id.toLocaleLowerCase().includes(needle),
      ),
    }))
    .filter((group) => group.items.length > 0);
}
