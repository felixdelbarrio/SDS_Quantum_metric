import { CalendarDays, Star } from "lucide-react";
import { AvailableCountry, CountryCode, DashboardCoverage } from "../types";
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
  dateRange: DateRange;
  coverage?: DashboardCoverage | null;
  missingIngestionPending: boolean;
  onCountryChange: (country: CountryCode) => void;
  onDateRangeChange: (range: DateRange) => void;
  onIngestMissingDays: () => void;
};

export function DashboardHeader({
  country,
  countries,
  dateRange,
  coverage,
  missingIngestionPending,
  onCountryChange,
  onDateRangeChange,
  onIngestMissingDays,
}: Props) {
  const warningLevel = coverage?.warning_level ?? "none";
  const showCoverage = warningLevel !== "none";
  const canIngestCoverage = showCoverage && !missingIngestionPending;
  return (
    <header className="dashboard-header">
      <div className="dashboard-title-group">
        <span className="dashboard-icon" aria-hidden="true">
          <Star size={18} />
        </span>
        <div>
          <h1>Dashboard General {country}</h1>
          <p>Este dashboard es un resumen de sesiones y errores.</p>
          {showCoverage ? (
            <div className={`coverage-pill ${warningLevel}`} role="status">
              <span>{coverage?.message}</span>
              <button
                className="text-command"
                type="button"
                onClick={onIngestMissingDays}
                disabled={!canIngestCoverage}
              >
                {missingIngestionPending
                  ? "Ingestando"
                  : dateRange.preset === "today"
                    ? "Actualizar hoy"
                    : "Ingestar periodo"}
              </button>
            </div>
          ) : null}
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
      </div>
    </header>
  );
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
