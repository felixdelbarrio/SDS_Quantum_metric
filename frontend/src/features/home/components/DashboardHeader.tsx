import { CalendarDays, Star } from "lucide-react";
import { AvailableCountry, CountryCode, DashboardCoverage } from "../types";
import { todayInTimezone } from "../timezone";
import { CountrySelector } from "./CountrySelector";

export type DatePreset = "today" | "yesterday" | "last_7_days" | "custom";

export type DateRange = {
  preset: DatePreset;
  startDate: string;
  endDate: string;
};

type Props = {
  country: CountryCode;
  timezone: string;
  countries: AvailableCountry[];
  dateRange: DateRange;
  coverage?: DashboardCoverage | null;
  dashboardName?: string | null;
  dashboardTitle?: string | null;
  dashboardDescription?: string | null;
  missingIngestionPending: boolean;
  onCountryChange: (country: CountryCode) => void;
  onDateRangeChange: (range: DateRange) => void;
  onIngestMissingDays: () => void;
};

export function DashboardHeader({
  country,
  timezone,
  countries,
  dateRange,
  coverage,
  dashboardName,
  dashboardTitle,
  dashboardDescription,
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
          <h1>
            {dashboardTitle ?? dashboardName ?? `Dashboard General ${country}`}
          </h1>
          <p>
            {dashboardDescription ??
              "Dashboard local generado desde Quantum Web."}
          </p>
          {dashboardName ? (
            <span className="dashboard-context">
              Dashboard: {dashboardName}
            </span>
          ) : null}
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
                  ? "Ingestando periodo..."
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
                  rangeForPreset(
                    event.target.value as DatePreset,
                    dateRange,
                    timezone,
                  ),
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

function rangeForPreset(
  preset: DatePreset,
  current: DateRange,
  timezone: string,
): DateRange {
  if (preset === "custom") return { ...current, preset };
  const today = todayInTimezone(timezone);
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

function addDays(value: string, days: number) {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function formatDateRange(range: DateRange) {
  if (range.startDate === range.endDate) return range.startDate;
  return `${range.startDate} - ${range.endDate}`;
}
