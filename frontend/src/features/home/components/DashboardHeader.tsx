import { Filter, Layers3, RefreshCcw, Star } from "lucide-react";
import { AvailableCountry, CountryCode, DashboardSelection } from "../types";
import { CountrySelector } from "./CountrySelector";

type Props = {
  country: CountryCode;
  countries: AvailableCountry[];
  appliedDimension?: DashboardSelection | null;
  appliedSegment?: DashboardSelection | null;
  onCountryChange: (country: CountryCode) => void;
  onOpenDimensions: () => void;
  onOpenSegments: () => void;
  onRefresh: () => void;
  isRefreshing: boolean;
};

export function DashboardHeader({
  country,
  countries,
  appliedDimension,
  appliedSegment,
  onCountryChange,
  onOpenDimensions,
  onOpenSegments,
  onRefresh,
  isRefreshing,
}: Props) {
  return (
    <header className="dashboard-header">
      <div className="dashboard-title-group">
        <span className="dashboard-icon" aria-hidden="true">
          <Star size={18} />
        </span>
        <div>
          <h1>Dashboard General {country}</h1>
          <p>Este dashboard es un resumen de sesiones y errores.</p>
          <div className="dashboard-applied">
            <span>Dimension: {appliedDimension?.label ?? "sin dimension"}</span>
            <span>Segmento: {appliedSegment?.label ?? "sin segmento"}</span>
          </div>
        </div>
      </div>

      <div className="dashboard-actions">
        <CountrySelector
          countries={countries}
          value={country}
          onChange={onCountryChange}
        />
        <button className="button secondary" onClick={onOpenDimensions}>
          <Layers3 size={16} /> Add Dashboard Dimension
        </button>
        <button className="button secondary" onClick={onOpenSegments}>
          <Filter size={16} /> Dashboard Segment
        </button>
        <button className="button" onClick={onRefresh} disabled={isRefreshing}>
          <RefreshCcw size={16} /> Actualizar
        </button>
      </div>
    </header>
  );
}
