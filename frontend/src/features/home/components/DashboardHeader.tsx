import { CalendarDays, Filter, Layers3, RefreshCcw, Star } from "lucide-react";
import { AvailableCountry, CountryCode, DashboardSelection } from "../types";
import { CountrySelector } from "./CountrySelector";

export type DatePreset = "today" | "yesterday" | "last_7_days" | "custom";

export type DateRange = {
  preset: DatePreset;
  startDate: string;
  endDate: string;
};

type Props = {
  country: CountryCode;
  countries: AvailableCountry[];
  countryStatus?: AvailableCountry;
  appliedDimension?: DashboardSelection | null;
  appliedSegment?: DashboardSelection | null;
  dateRange: DateRange;
  onCountryChange: (country: CountryCode) => void;
  onDateRangeChange: (range: DateRange) => void;
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
  dateRange,
  onCountryChange,
  onDateRangeChange,
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
        <div className="date-filter" aria-label="Rango de fechas local">
          <label>
            <span>Fecha</span>
            <select
              value={dateRange.preset}
              onChange={(event) =>
                onDateRangeChange(
                  rangeForPreset(event.target.value as DatePreset, dateRange),
                )
              }
            >
              <option value="today">Hoy</option>
              <option value="yesterday">Ayer</option>
              <option value="last_7_days">Ultimos 7 dias</option>
              <option value="custom">Rango</option>
            </select>
          </label>
          {dateRange.preset === "custom" ? (
            <>
              <input
                type="date"
                value={dateRange.startDate}
                onChange={(event) =>
                  onDateRangeChange({
                    ...dateRange,
                    startDate: event.target.value,
                  })
                }
                aria-label="Fecha inicial"
              />
              <input
                type="date"
                value={dateRange.endDate}
                onChange={(event) =>
                  onDateRangeChange({
                    ...dateRange,
                    endDate: event.target.value,
                  })
                }
                aria-label="Fecha final"
              />
            </>
          ) : (
            <span className="date-filter-label">
              <CalendarDays size={14} />
              {formatDateRange(dateRange)}
            </span>
          )}
        </div>
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

function rangeForPreset(preset: DatePreset, current: DateRange): DateRange {
  if (preset === "custom") return { ...current, preset };
  const today = todayInMexico();
  if (preset === "today") {
    return { preset, startDate: today, endDate: today };
  }
  if (preset === "yesterday") {
    const yesterday = addDays(today, -1);
    return { preset, startDate: yesterday, endDate: yesterday };
  }
  const start = addDays(today, -6);
  return { preset, startDate: start, endDate: today };
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

function formatDateRange(range: DateRange) {
  if (range.startDate === range.endDate) return range.startDate;
  return `${range.startDate} - ${range.endDate}`;
}
