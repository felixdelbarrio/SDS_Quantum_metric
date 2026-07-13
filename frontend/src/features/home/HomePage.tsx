import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { getCountries, getCoverage, getDashboard, ingestRange } from "./api";
import { DashboardHeader } from "./components/DashboardHeader";
import { DateRange } from "./components/DashboardHeader";
import { DashboardTabs } from "./components/DashboardTabs";
import { EmptyAnalyticsState } from "./components/EmptyAnalyticsState";
import {
  CountryCode,
  DashboardCoverage,
  DynamicDashboardResponse,
} from "./types";
import { DashboardSectionGrid } from "./components/DashboardSectionGrid";
import { COUNTRY_OPTIONS } from "../../shared/countries";
import { useAppStore } from "../../shared/state/appStore";
import { timezoneForCountry, todayInTimezone } from "./timezone";
import { normalizeDashboardDisplayText } from "./displayText";

const COUNTRY_CODES = COUNTRY_OPTIONS.map((country) => country.code);

export function HomePage() {
  const queryClient = useQueryClient();
  const { activeCountry, hasCountryPreference, setActiveCountry } =
    useAppStore();
  const country = asCountryCode(activeCountry);
  const [activeTab, setActiveTab] = useState<string>("");
  const [dateRange, setDateRange] = useState<DateRange>(() => {
    const today = todayInTimezone(timezoneForCountry(country));
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
  const selectedCountryMeta = countries.data?.countries.find(
    (item) => item.code === selectedCountry,
  );
  const dashboardTimezone =
    selectedCountryMeta?.timezone ?? timezoneForCountry(selectedCountry);
  useEffect(() => {
    setDateRange((current) => dateRangeForTimezone(current, dashboardTimezone));
  }, [dashboardTimezone]);
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

  const dashboard = useQuery({
    queryKey: [
      "dashboard",
      "dynamic",
      selectedCountry,
      dateRange.startDate,
      dateRange.endDate,
      dateRange.preset,
    ],
    queryFn: () =>
      getDashboard({
        country: selectedCountry,
        startDate: dateRange.startDate,
        endDate: dateRange.endDate,
        rangeKey: dateRange.preset,
      }),
    select: normalizeDashboardDisplayText,
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

  useEffect(() => {
    const firstTab = dashboard.data?.tabs?.[0]?.tab;
    if (!firstTab) return;
    if (!dashboard.data?.tabs.some((tab) => tab.tab === activeTab)) {
      setActiveTab(firstTab);
    }
  }, [activeTab, dashboard.data?.tabs]);

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
        timezone={dashboardTimezone}
        countries={countries.data.countries}
        dateRange={dateRange}
        coverage={coverage.data}
        dashboardName={
          dashboard.data?.dashboard_name ?? selectedCountryMeta?.dashboard_name
        }
        dashboardTitle={dashboard.data?.dashboard_title}
        dashboardDescription={dashboard.data?.description}
        missingIngestionPending={rangeIngestionMutation.isPending}
        onCountryChange={setActiveCountry}
        onDateRangeChange={setDateRange}
        onIngestMissingDays={() => rangeIngestionMutation.mutate()}
      />

      <DashboardTabs
        tabs={dashboard.data?.tabs ?? []}
        active={activeTab || dashboard.data?.tabs?.[0]?.tab || ""}
        onChange={setActiveTab}
      />

      <DynamicDashboardTabPanel
        activeTab={activeTab || dashboard.data?.tabs?.[0]?.tab || ""}
        response={dashboard.data}
        isLoading={dashboard.isLoading}
      />
    </div>
  );
}

function DynamicDashboardTabPanel({
  activeTab,
  response,
  isLoading,
}: {
  activeTab: string;
  response?: DynamicDashboardResponse;
  isLoading: boolean;
}) {
  if (isLoading) {
    return <div className="analytics-loading">Cargando dashboard</div>;
  }
  const tabs = response?.tabs ?? [];
  const tab = tabs.find((item) => item.tab === activeTab) ?? tabs[0];
  const sections = tab?.sections ?? [];
  if (!sections.some((section) => section.widgets.length)) {
    return (
      <div className="dashboard-tab-panel">
        <EmptyAnalyticsState reason={response?.reason} />
      </div>
    );
  }
  return (
    <div className="dashboard-tab-panel">
      {sections.map((section, sectionIndex) => (
        <DashboardSectionGrid
          key={section.section_id ?? `section-${sectionIndex}`}
          section={section}
          sectionIndex={sectionIndex}
        />
      ))}
    </div>
  );
}

function addDays(value: string, days: number) {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function dateRangeForTimezone(current: DateRange, timezone: string): DateRange {
  if (current.preset === "custom") return current;
  const today = todayInTimezone(timezone);
  if (current.preset === "today") {
    return { ...current, startDate: today, endDate: today };
  }
  if (current.preset === "yesterday") {
    const yesterday = addDays(today, -1);
    return { ...current, startDate: yesterday, endDate: yesterday };
  }
  return { ...current, startDate: addDays(today, -6), endDate: today };
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
