import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  getCountries,
  getCoverage,
  getErrors,
  getSummary,
  ingestRange,
} from "./api";
import { DashboardHeader } from "./components/DashboardHeader";
import { DateRange } from "./components/DashboardHeader";
import { DashboardTabs } from "./components/DashboardTabs";
import { EmptyAnalyticsState } from "./components/EmptyAnalyticsState";
import { ErrorsTab } from "./components/ErrorsTab";
import { SummaryTab } from "./components/SummaryTab";
import { CountryCode, DashboardCoverage } from "./types";
import { COUNTRY_OPTIONS } from "../../shared/countries";
import { useAppStore } from "../../shared/state/appStore";

type DashboardTab = "summary" | "errors";

const COUNTRY_CODES = COUNTRY_OPTIONS.map((country) => country.code);

export function HomePage() {
  const queryClient = useQueryClient();
  const { activeCountry, hasCountryPreference, setActiveCountry } =
    useAppStore();
  const country = asCountryCode(activeCountry);
  const [activeTab, setActiveTab] = useState<DashboardTab>("summary");
  const [dateRange, setDateRange] = useState<DateRange>(() => {
    const today = todayInMexico();
    return {
      preset: "last_7_days",
      startDate: addDays(today, -6),
      endDate: today,
    };
  });
  const countries = useQuery({
    queryKey: ["dashboard", "countries"],
    queryFn: getCountries,
  });

  const hasDashboardData = Boolean(countries.data?.countries?.length);
  const selectedCountry = useMemo(() => {
    if (!countries.data?.countries.length) return country;
    if (countries.data.countries.some((item) => item.code === country)) {
      return country;
    }
    const defaultCountry = countries.data.countries.find(
      (item) => item.code === countries.data?.default_country,
    );
    return defaultCountry?.code ?? countries.data.countries[0].code;
  }, [countries.data, country]);
  useEffect(() => {
    if (!countries.data?.countries.length) return;
    if (
      !hasCountryPreference ||
      !countries.data.countries.some((item) => item.code === country)
    ) {
      setActiveCountry(selectedCountry);
    }
  }, [
    countries.data,
    country,
    hasCountryPreference,
    selectedCountry,
    setActiveCountry,
  ]);

  const summary = useQuery({
    queryKey: [
      "dashboard",
      "summary",
      selectedCountry,
      dateRange.startDate,
      dateRange.endDate,
      dateRange.preset,
    ],
    queryFn: () =>
      getSummary({
        country: selectedCountry,
        startDate: dateRange.startDate,
        endDate: dateRange.endDate,
        rangeKey: dateRange.preset,
      }),
    enabled: hasDashboardData,
  });

  const coverage = useQuery({
    queryKey: [
      "dashboard",
      "coverage",
      selectedCountry,
      dateRange.startDate,
      dateRange.endDate,
      dateRange.preset,
    ],
    queryFn: () =>
      getCoverage({
        country: selectedCountry,
        startDate: dateRange.startDate,
        endDate: dateRange.endDate,
        rangeKey: dateRange.preset,
      }),
    enabled: hasDashboardData,
  });

  const errors = useQuery({
    queryKey: [
      "dashboard",
      "errors",
      selectedCountry,
      dateRange.startDate,
      dateRange.endDate,
      dateRange.preset,
    ],
    queryFn: () =>
      getErrors({
        country: selectedCountry,
        startDate: dateRange.startDate,
        endDate: dateRange.endDate,
        rangeKey: dateRange.preset,
      }),
    enabled: activeTab === "errors" && hasDashboardData,
  });

  const rangeIngestionMutation = useMutation({
    mutationFn: () =>
      ingestRange(selectedCountry, {
        rangeKey: dateRange.preset,
        startDate: dateRange.startDate,
        endDate: dateRange.endDate,
        reason: coverageIngestionReason(coverage.data),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      void queryClient.invalidateQueries({ queryKey: ["ingestions"] });
    },
  });

  if (countries.isLoading) {
    return <div className="analytics-loading">Cargando paises</div>;
  }

  if (countries.isError || !countries.data) {
    return (
      <EmptyAnalyticsState
        title="No se pudo cargar el dashboard"
        reason="La API local de paises no respondio correctamente."
      />
    );
  }

  if (!countries.data.countries.length) {
    return (
      <div className="dashboard-page">
        <header className="page-header">
          <h1>Dashboard General {selectedCountry}</h1>
        </header>
        <EmptyAnalyticsState
          title="Sin datos ingestados"
          reason="No hay datos locales reproducibles. Ejecuta una ingesta o una regresion para capturar las cards obligatorias."
        />
      </div>
    );
  }

  return (
    <div className="dashboard-page">
      <DashboardHeader
        country={selectedCountry}
        countries={countries.data.countries}
        dateRange={dateRange}
        coverage={coverage.data}
        missingIngestionPending={rangeIngestionMutation.isPending}
        onCountryChange={setActiveCountry}
        onDateRangeChange={setDateRange}
        onIngestMissingDays={() => rangeIngestionMutation.mutate()}
      />

      <DashboardTabs active={activeTab} onChange={setActiveTab} />

      {activeTab === "summary" ? (
        <SummaryTab
          country={selectedCountry}
          dateRange={dateRange}
          response={summary.data}
          isLoading={summary.isLoading}
        />
      ) : (
        <ErrorsTab
          country={selectedCountry}
          dateRange={dateRange}
          response={errors.data}
          isLoading={errors.isLoading}
        />
      )}
    </div>
  );
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

function asCountryCode(value: string): CountryCode {
  return COUNTRY_CODES.includes(value as CountryCode)
    ? (value as CountryCode)
    : "MX";
}

function coverageIngestionReason(coverage?: DashboardCoverage) {
  if (coverage?.data_quality) return coverage.data_quality;
  if (coverage?.missing_days?.length) return "missing_days";
  return "user_requested";
}
