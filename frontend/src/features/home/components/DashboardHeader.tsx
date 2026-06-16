import { Filter, Layers3, RefreshCcw, Star } from "lucide-react";
import { AvailableCountry, CountryCode, DashboardSelection } from "../types";
import { CountrySelector } from "./CountrySelector";

type Props = {
  country: CountryCode;
  countries: AvailableCountry[];
  countryStatus?: AvailableCountry;
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
  countryStatus,
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
          <div className="dataset-facts compact">
            <span>{formatNumber(countryStatus?.raw_calls)} calls</span>
            <span>{formatNumber(countryStatus?.rows)} filas</span>
            <span>{formatNumber(countryStatus?.cards)} cards</span>
            <span>{countryStatus?.regression_status ?? "sin regresion"}</span>
          </div>
        </div>
      </div>

      <div className="dashboard-actions command-bar">
        <CountrySelector
          countries={countries}
          value={country}
          onChange={onCountryChange}
        />
        <div className="command-group">
          <button className="command-button" onClick={onOpenDimensions}>
            <Layers3 size={16} /> Dimension
          </button>
          <button className="command-button" onClick={onOpenSegments}>
            <Filter size={16} /> Segmento
          </button>
          <button
            className="command-button primary"
            onClick={onRefresh}
            disabled={isRefreshing}
          >
            <RefreshCcw size={16} /> Actualizar
          </button>
        </div>
      </div>
    </header>
  );
}

function formatNumber(value?: number | null) {
  return value == null ? "0" : value.toLocaleString();
}
