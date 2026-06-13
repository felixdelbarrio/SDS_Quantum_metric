import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  getCountries,
  getDimensions,
  getErrors,
  getSegments,
  getSummary,
} from "./api";
import { DashboardHeader } from "./components/DashboardHeader";
import { DashboardTabs } from "./components/DashboardTabs";
import { DimensionPicker } from "./components/DimensionPicker";
import { EmptyAnalyticsState } from "./components/EmptyAnalyticsState";
import { ErrorsTab } from "./components/ErrorsTab";
import { SegmentPicker } from "./components/SegmentPicker";
import { SummaryTab } from "./components/SummaryTab";
import {
  CountryCode,
  DashboardDimensionGroup,
  DashboardSelection,
  DashboardSegment,
} from "./types";
import { useAppStore } from "../../shared/state/appStore";

type DashboardTab = "summary" | "errors";

const COUNTRY_CODES: CountryCode[] = ["ES", "MX", "PE", "CO", "AR"];

export function HomePage() {
  const queryClient = useQueryClient();
  const { activeCountry, hasCountryPreference, setActiveCountry } =
    useAppStore();
  const country = asCountryCode(activeCountry);
  const [activeTab, setActiveTab] = useState<DashboardTab>("summary");
  const [dimension, setDimension] = useState<string | null>(null);
  const [segment, setSegment] = useState<string | null>(null);
  const [dimensionPanelOpen, setDimensionPanelOpen] = useState(false);
  const [segmentPanelOpen, setSegmentPanelOpen] = useState(false);

  const countries = useQuery({
    queryKey: ["dashboard", "countries"],
    queryFn: getCountries,
  });

  useEffect(() => {
    if (!countries.data || hasCountryPreference) return;
    if (countries.data.default_country !== country) {
      setActiveCountry(countries.data.default_country);
    }
  }, [countries.data, country, hasCountryPreference, setActiveCountry]);

  useEffect(() => {
    setSegment(null);
  }, [country]);

  const summary = useQuery({
    queryKey: ["dashboard", "summary", country, dimension, segment],
    queryFn: () => getSummary({ country, dimension, segment }),
  });

  const errors = useQuery({
    queryKey: ["dashboard", "errors", country, dimension, segment],
    queryFn: () => getErrors({ country, dimension, segment }),
    enabled: activeTab === "errors",
  });

  const dimensions = useQuery({
    queryKey: ["dashboard", "dimensions", country],
    queryFn: () => getDimensions(country),
  });

  const segments = useQuery({
    queryKey: ["dashboard", "segments", country],
    queryFn: () => getSegments(country),
  });

  const appliedDimension = useMemo(
    () =>
      summary.data?.applied_dimension ??
      findDimensionSelection(dimensions.data?.groups ?? [], dimension),
    [dimension, dimensions.data?.groups, summary.data?.applied_dimension],
  );
  const appliedSegment = useMemo(
    () =>
      summary.data?.applied_segment ??
      findSegmentSelection(segments.data?.segments ?? [], segment),
    [segment, segments.data?.segments, summary.data?.applied_segment],
  );

  function refreshDashboard() {
    void countries.refetch();
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  }

  function applyDimension(nextDimension: string) {
    setDimension(nextDimension);
    setDimensionPanelOpen(false);
  }

  function clearDimension() {
    setDimension(null);
    setDimensionPanelOpen(false);
  }

  function applySegment(nextSegment: string) {
    setSegment(nextSegment);
    setSegmentPanelOpen(false);
  }

  function clearSegment() {
    setSegment(null);
    setSegmentPanelOpen(false);
  }

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

  return (
    <div className="dashboard-page">
      <DashboardHeader
        country={country}
        countries={countries.data.countries}
        appliedDimension={appliedDimension}
        appliedSegment={appliedSegment}
        onCountryChange={setActiveCountry}
        onOpenDimensions={() => setDimensionPanelOpen(true)}
        onOpenSegments={() => setSegmentPanelOpen(true)}
        onRefresh={refreshDashboard}
        isRefreshing={summary.isFetching || errors.isFetching}
      />

      <DashboardTabs active={activeTab} onChange={setActiveTab} />

      {activeTab === "summary" ? (
        <SummaryTab
          country={country}
          dimension={dimension}
          segment={segment}
          response={summary.data}
          isLoading={summary.isLoading}
        />
      ) : (
        <ErrorsTab
          country={country}
          dimension={dimension}
          segment={segment}
          response={errors.data}
          isLoading={errors.isLoading}
        />
      )}

      <DimensionPicker
        open={dimensionPanelOpen}
        response={dimensions.data}
        selected={appliedDimension}
        isLoading={dimensions.isLoading}
        onApply={applyDimension}
        onClear={clearDimension}
        onClose={() => setDimensionPanelOpen(false)}
      />

      <SegmentPicker
        open={segmentPanelOpen}
        response={segments.data}
        selected={appliedSegment}
        isLoading={segments.isLoading}
        onApply={applySegment}
        onClear={clearSegment}
        onClose={() => setSegmentPanelOpen(false)}
      />
    </div>
  );
}

function asCountryCode(value: string): CountryCode {
  return COUNTRY_CODES.includes(value as CountryCode)
    ? (value as CountryCode)
    : "MX";
}

function findDimensionSelection(
  groups: DashboardDimensionGroup[],
  selectedId: string | null,
): DashboardSelection | null {
  if (!selectedId) return null;
  for (const group of groups) {
    const item = group.items.find((dimension) => dimension.id === selectedId);
    if (item) return { id: item.id, label: item.label };
  }
  return { id: selectedId, label: selectedId };
}

function findSegmentSelection(
  segments: DashboardSegment[],
  selectedId: string | null,
): DashboardSelection | null {
  if (!selectedId) return null;
  const item = segments.find((segment) => segment.id === selectedId);
  return item
    ? { id: item.id, label: item.label }
    : { id: selectedId, label: selectedId };
}
