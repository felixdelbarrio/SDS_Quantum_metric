from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

import polars as pl

from backend.app.analytics.dimensions import build_dimension_groups
from backend.app.analytics.errors import calculate_error_rows
from backend.app.analytics.models import (
    AvailableCountry,
    DashboardComparison,
    DashboardCountrySelection,
    DashboardDimensionsResponse,
    DashboardSegmentsResponse,
    DashboardSelection,
    DetailTableResponse,
    DetailTableRow,
    EmptyAnalyticsResponse,
    ErrorComparisonResponse,
    ErrorComparisonWidget,
    ErrorPercentageWidget,
    ErrorsDashboardResponse,
    ErrorSeriesPoint,
    KpiBreakdownItem,
    KpiWidget,
    SortDirection,
    SummaryDashboardResponse,
    TableColumn,
    TimeseriesPoint,
)
from backend.app.analytics.normalizer import (
    NormalizedDataset,
    NormalizedRecord,
    humanize_key,
    normalize_raw_calls,
)
from backend.app.analytics.segments import build_segments, parse_segment
from backend.app.quantum.schemas import Country
from backend.app.storage.parquet_store import ParquetStore

COUNTRY_LABELS = {
    Country.ES.value: "Espana",
    Country.MX.value: "Mexico",
    Country.PE.value: "Peru",
    Country.CO.value: "Colombia",
    Country.AR.value: "Argentina",
}

SUMMARY_COLUMNS = [
    TableColumn(key="name", label="name", sortable=True),
    TableColumn(key="app_name", label="App Name", sortable=True),
    TableColumn(key="operating_system", label="Sistema operativo", sortable=True),
    TableColumn(key="page_views", label="Page Views", sortable=True),
    TableColumn(key="sessions", label="Sessions", sortable=True),
    TableColumn(key="conversions", label="General - Conversiones", sortable=True),
]

ERROR_COLUMNS = [
    TableColumn(key="name", label="App Name", sortable=True),
    TableColumn(key="sessions", label="Sessions", sortable=True),
    TableColumn(key="sessions_with_error", label="Sessions with Error", sortable=True),
    TableColumn(key="error_session_percent", label="% Sesiones con Error", sortable=True),
]


class AnalyticsQueryEngine:
    def __init__(self, store: ParquetStore) -> None:
        self.store = store

    def countries(self) -> DashboardCountrySelection:
        countries: list[AvailableCountry] = []
        first_with_data: str | None = None
        for code in COUNTRY_LABELS:
            raw_calls = self._read_raw_calls(code)
            rows = _sum_row_counts(raw_calls)
            last_ingestion_at = _last_ingestion(raw_calls)
            has_data = bool(raw_calls)
            if has_data and first_with_data is None:
                first_with_data = code
            countries.append(
                AvailableCountry(
                    code=code,
                    label=COUNTRY_LABELS[code],
                    has_data=has_data,
                    raw_calls=len(raw_calls),
                    rows=rows,
                    last_ingestion_at=last_ingestion_at,
                )
            )

        configured = str(self.store.settings.qm_country or Country.MX.value)
        default_country = first_with_data or (
            configured if configured in COUNTRY_LABELS else Country.MX.value
        )
        return DashboardCountrySelection(countries=countries, default_country=default_country)

    def dimensions(self, country: str) -> DashboardDimensionsResponse:
        dataset = self.load(country)
        return DashboardDimensionsResponse(
            country=country,
            groups=build_dimension_groups(dataset.discovered_dimensions),
        )

    def segments(self, country: str) -> DashboardSegmentsResponse:
        dataset = self.load(country)
        return DashboardSegmentsResponse(country=country, segments=build_segments(dataset.records))

    def summary(
        self,
        country: str,
        dimension: str | None = None,
        segment: str | None = None,
    ) -> SummaryDashboardResponse:
        dataset = self.load(country)
        empty = self._empty_if_needed(dataset)
        if empty:
            return SummaryDashboardResponse(
                status="empty",
                country=country,
                reason=empty.reason,
                required_dataset=empty.required_dataset,
                available_datasets=empty.available_datasets,
            )

        records = self._apply_segment(dataset.records, segment)
        if not records:
            return self._empty_summary(
                country,
                "No local rows match the selected dashboard segment.",
                dataset.available_datasets,
                dimension,
                segment,
                dataset,
            )

        widgets = [
            self._kpi_widget(
                records,
                "page_views",
                "Paginas vistas",
                "count",
                dimension,
            ),
            self._kpi_widget(records, "sessions", "Sesiones", "count", dimension),
            self._kpi_widget(
                records,
                "converted_sessions",
                "Sesiones con conversion",
                "count",
                dimension,
            ),
            self._kpi_widget(
                records,
                "avg_session_time",
                "Tiempo medio de sesion",
                "seconds",
                dimension,
            ),
        ]
        if not any(widget.value is not None for widget in widgets):
            return self._empty_summary(
                country,
                "Parseable rows do not contain supported summary metric fields.",
                dataset.available_datasets,
                dimension,
                segment,
                dataset,
            )

        return SummaryDashboardResponse(
            status="ok",
            country=country,
            last_ingestion_at=dataset.last_ingestion_at,
            applied_dimension=self._dimension_selection(dataset, dimension),
            applied_segment=self._segment_selection(dataset.records, segment),
            widgets=widgets,
            available_datasets=dataset.available_datasets,
        )

    def summary_table(
        self,
        country: str,
        search: str | None = None,
        sort: str = "page_views",
        direction: SortDirection = "desc",
        dimension: str | None = None,
        segment: str | None = None,
    ) -> DetailTableResponse:
        dataset = self.load(country)
        empty = self._empty_if_needed(dataset)
        if empty:
            return DetailTableResponse(
                status="empty",
                country=country,
                columns=SUMMARY_COLUMNS,
                reason=empty.reason,
                required_dataset=empty.required_dataset,
                available_datasets=empty.available_datasets,
            )

        records = self._apply_segment(dataset.records, segment)
        group_dimension = dimension or "app_name"
        rows = self._summary_rows(records, group_dimension)
        rows = self._filter_summary_rows(rows, search)
        rows = self._sort_rows(rows, sort, direction)

        return DetailTableResponse(
            status="ok" if rows else "empty",
            country=country,
            columns=SUMMARY_COLUMNS,
            rows=[DetailTableRow.model_validate(row) for row in rows],
            applied_dimension=self._dimension_selection(dataset, dimension),
            applied_segment=self._segment_selection(dataset.records, segment),
            reason=None if rows else "No local summary rows match the selected filters.",
            available_datasets=dataset.available_datasets,
        )

    def errors(
        self,
        country: str,
        dimension: str | None = None,
        segment: str | None = None,
    ) -> ErrorsDashboardResponse:
        dataset = self.load(country)
        empty = self._empty_if_needed(dataset)
        if empty:
            return ErrorsDashboardResponse(
                status="empty",
                country=country,
                reason=empty.reason,
                required_dataset=empty.required_dataset,
                available_datasets=empty.available_datasets,
            )

        records = self._apply_segment(dataset.records, segment)
        group_dimension = dimension or "app_name"
        rows = calculate_error_rows(records, group_dimension)
        if not rows:
            return ErrorsDashboardResponse(
                status="empty",
                country=country,
                last_ingestion_at=dataset.last_ingestion_at,
                applied_dimension=self._dimension_selection(dataset, dimension),
                applied_segment=self._segment_selection(dataset.records, segment),
                reason="Parseable rows do not contain supported error metric fields.",
                required_dataset="raw_api_calls",
                available_datasets=dataset.available_datasets,
            )

        total_errors = sum(row.sessions_with_error or 0.0 for row in rows)
        series = [
            ErrorSeriesPoint(
                name=row.name,
                value=row.sessions_with_error or 0.0,
                percent=round(((row.sessions_with_error or 0.0) / total_errors) * 100, 2)
                if total_errors
                else 0.0,
            )
            for row in rows
            if row.sessions_with_error is not None
        ]
        series.sort(key=lambda item: item.value, reverse=True)

        percent_rows = sorted(
            rows,
            key=lambda row: (
                row.error_session_percent if row.error_session_percent is not None else -1
            ),
            reverse=True,
        )
        return ErrorsDashboardResponse(
            status="ok",
            country=country,
            last_ingestion_at=dataset.last_ingestion_at,
            applied_dimension=self._dimension_selection(dataset, dimension),
            applied_segment=self._segment_selection(dataset.records, segment),
            widgets=[
                ErrorComparisonWidget(
                    id="error_sessions_by_app_name",
                    title="Comparativa de sesiones con error por App Name",
                    chart_type="donut",
                    total=total_errors if total_errors else None,
                    series=series,
                    comparison=self._comparison(records, "sessions_with_error"),
                ),
                ErrorPercentageWidget(
                    id="error_session_percentage_by_app_name",
                    title="% Sesiones con Error por App Name",
                    chart_type="table",
                    rows=percent_rows,
                ),
            ],
            available_datasets=dataset.available_datasets,
        )

    def errors_table(
        self,
        country: str,
        search: str | None = None,
        sort: str = "error_session_percent",
        direction: SortDirection = "desc",
        dimension: str | None = None,
        segment: str | None = None,
    ) -> ErrorComparisonResponse:
        dataset = self.load(country)
        empty = self._empty_if_needed(dataset)
        if empty:
            return ErrorComparisonResponse(
                status="empty",
                country=country,
                columns=ERROR_COLUMNS,
                reason=empty.reason,
                required_dataset=empty.required_dataset,
                available_datasets=empty.available_datasets,
            )

        records = self._apply_segment(dataset.records, segment)
        rows = calculate_error_rows(records, dimension or "app_name")
        rows = [row for row in rows if not search or search.casefold() in row.name.casefold()]
        rows.sort(
            key=lambda row: _error_sort_value(row, sort),
            reverse=direction == "desc",
        )
        return ErrorComparisonResponse(
            status="ok" if rows else "empty",
            country=country,
            columns=ERROR_COLUMNS,
            rows=rows,
            applied_dimension=self._dimension_selection(dataset, dimension),
            applied_segment=self._segment_selection(dataset.records, segment),
            reason=None if rows else "No local error rows match the selected filters.",
            available_datasets=dataset.available_datasets,
        )

    def load(self, country: str) -> NormalizedDataset:
        available = self._available_dataset_names(country)
        return normalize_raw_calls(country, self._read_raw_calls(country), available)

    def _read_raw_calls(self, country: str) -> list[dict[str, Any]]:
        root = self.store.settings.parquet_dir / f"country={country}" / "raw_api_calls"
        files = sorted(root.rglob("*.parquet")) if root.exists() else []
        if not files:
            return []
        frames: list[pl.DataFrame] = []
        for file in files:
            frames.append(pl.read_parquet(file))
        if not frames:
            return []
        return pl.concat(frames, how="diagonal_relaxed").to_dicts()

    def _available_dataset_names(self, country: str) -> list[str]:
        root = self.store.settings.parquet_dir / f"country={country}"
        if not root.exists():
            return []
        names: set[str] = set()
        for file in root.rglob("*.parquet"):
            names.add(str(file.parent.relative_to(self.store.settings.parquet_dir)))
        return sorted(names)

    def _empty_if_needed(self, dataset: NormalizedDataset) -> EmptyAnalyticsResponse | None:
        if dataset.raw_calls == 0:
            return EmptyAnalyticsResponse(
                country=dataset.country,
                reason="No local Parquet rows available for requested country.",
                required_dataset="raw_api_calls",
                available_datasets=dataset.available_datasets,
            )
        if not dataset.has_parseable_rows:
            return EmptyAnalyticsResponse(
                country=dataset.country,
                reason=(
                    "Local raw_api_calls exist, but response_json does not contain "
                    "parseable analytics rows."
                ),
                required_dataset="raw_api_calls.response_json.rows",
                available_datasets=dataset.available_datasets,
            )
        return None

    def _empty_summary(
        self,
        country: str,
        reason: str,
        available_datasets: list[str],
        dimension: str | None,
        segment: str | None,
        dataset: NormalizedDataset,
    ) -> SummaryDashboardResponse:
        return SummaryDashboardResponse(
            status="empty",
            country=country,
            last_ingestion_at=dataset.last_ingestion_at,
            applied_dimension=self._dimension_selection(dataset, dimension),
            applied_segment=self._segment_selection(dataset.records, segment),
            reason=reason,
            required_dataset="raw_api_calls.response_json.rows",
            available_datasets=available_datasets,
        )

    def _kpi_widget(
        self,
        records: list[NormalizedRecord],
        metric: str,
        title: str,
        unit: Literal["count", "seconds", "percent"],
        dimension: str | None,
    ) -> KpiWidget:
        value = self._metric_value(records, metric)
        return KpiWidget(
            id=metric,
            title=title,
            value=value,
            unit=unit,
            breakdown=self._breakdown(records, metric, dimension),
            timeseries=self._timeseries(records, metric),
            comparison=self._comparison(records, metric),
            missing_source_field=None if value is not None else metric,
        )

    def _metric_value(self, records: list[NormalizedRecord], metric: str) -> float | None:
        if metric == "avg_session_time":
            weighted_total = 0.0
            weight = 0.0
            values: list[float] = []
            for record in records:
                duration = record.metric(metric)
                if duration is None:
                    continue
                sessions = record.metric("sessions")
                if sessions is not None and sessions > 0:
                    weighted_total += duration * sessions
                    weight += sessions
                else:
                    values.append(duration)
            if weight:
                return round(weighted_total / weight, 2)
            if values:
                return round(sum(values) / len(values), 2)
            return None
        return _sum_metric(records, metric)

    def _breakdown(
        self,
        records: list[NormalizedRecord],
        metric: str,
        dimension: str | None,
    ) -> list[KpiBreakdownItem]:
        value = self._metric_value(records, metric)
        if value is None:
            return []

        candidates = [dimension] if dimension else ["application_type", "device_type", "platform"]
        breakdown_dimension = next(
            (
                candidate
                for candidate in candidates
                if candidate and any(record.dimension(candidate) for record in records)
            ),
            None,
        )
        if not breakdown_dimension:
            return []

        buckets: dict[str, float] = defaultdict(float)
        for record in records:
            label = record.dimension(breakdown_dimension)
            metric_value = record.metric(metric)
            if label and metric_value is not None:
                buckets[_display_bucket(label)] += metric_value
        return [
            KpiBreakdownItem(label=label, value=round(bucket_value, 2))
            for label, bucket_value in sorted(
                buckets.items(), key=lambda item: item[1], reverse=True
            )
        ]

    def _timeseries(self, records: list[NormalizedRecord], metric: str) -> list[TimeseriesPoint]:
        buckets: dict[str, float] = defaultdict(float)
        for record in records:
            value = record.metric(metric)
            ts = record.period_start or record.ingestion_ts
            if value is None or not ts:
                continue
            buckets[ts] += value
        return [
            TimeseriesPoint(ts=ts, value=round(value, 2)) for ts, value in sorted(buckets.items())
        ]

    def _comparison(
        self,
        records: list[NormalizedRecord],
        metric: str,
    ) -> DashboardComparison | None:
        deltas = [
            delta
            for record in records
            if (delta := record.metric(f"{metric}_delta_percent")) is not None
        ]
        if not deltas:
            return None
        return DashboardComparison(
            label="Historical Range",
            delta_percent=round(sum(deltas) / len(deltas), 2),
        )

    def _summary_rows(
        self,
        records: list[NormalizedRecord],
        group_dimension: str,
    ) -> list[dict[str, Any]]:
        groups: dict[tuple[str, str | None], list[NormalizedRecord]] = defaultdict(list)
        for record in records:
            name = record.dimension(group_dimension) or record.dimension("app_name") or "Null"
            operating_system = record.dimension("operating_system")
            groups[(name, operating_system)].append(record)

        rows: list[dict[str, Any]] = []
        for (name, operating_system), grouped_records in groups.items():
            row: dict[str, Any] = {
                "name": name,
                "app_name": name if group_dimension == "app_name" else None,
                "operating_system": operating_system,
                "page_views": _sum_metric(grouped_records, "page_views"),
                "sessions": _sum_metric(grouped_records, "sessions"),
                "conversions": _sum_metric(grouped_records, "converted_sessions"),
                "page_views_delta_percent": _avg_metric(
                    grouped_records, "page_views_delta_percent"
                ),
                "conversions_delta_percent": _avg_metric(
                    grouped_records, "conversions_delta_percent"
                ),
            }
            if any(row[key] is not None for key in ("page_views", "sessions", "conversions")):
                rows.append(row)
        return rows

    def _filter_summary_rows(
        self,
        rows: list[dict[str, Any]],
        search: str | None,
    ) -> list[dict[str, Any]]:
        if not search:
            return rows
        needle = search.casefold()
        return [
            row
            for row in rows
            if any(
                needle in str(row.get(key) or "").casefold()
                for key in ("name", "app_name", "operating_system")
            )
        ]

    def _sort_rows(
        self,
        rows: list[dict[str, Any]],
        sort: str,
        direction: SortDirection,
    ) -> list[dict[str, Any]]:
        sortable_keys = {column.key for column in SUMMARY_COLUMNS}
        sort_key = sort if sort in sortable_keys else "page_views"
        return sorted(
            rows,
            key=lambda row: _sort_value(row.get(sort_key)),
            reverse=direction == "desc",
        )

    def _apply_segment(
        self,
        records: list[NormalizedRecord],
        segment: str | None,
    ) -> list[NormalizedRecord]:
        parsed = parse_segment(segment)
        if not parsed:
            return records
        field, value = parsed
        if field == "error_state":
            return [
                record
                for record in records
                if _matches_metric_state(record.metric("sessions_with_error"), value)
            ]
        if field == "conversion_state":
            return [
                record
                for record in records
                if _matches_metric_state(record.metric("converted_sessions"), value)
            ]
        return [record for record in records if record.dimension(field) == value]

    def _dimension_selection(
        self,
        dataset: NormalizedDataset,
        dimension: str | None,
    ) -> DashboardSelection | None:
        if not dimension:
            return None
        label = dataset.discovered_dimensions.get(dimension) or humanize_key(dimension)
        return DashboardSelection(id=dimension, label=label)

    def _segment_selection(
        self,
        records: list[NormalizedRecord],
        segment: str | None,
    ) -> DashboardSelection | None:
        if not segment:
            return None
        for item in build_segments(records):
            if item.id == segment:
                return DashboardSelection(id=item.id, label=item.label)
        parsed = parse_segment(segment)
        if parsed:
            field, value = parsed
            return DashboardSelection(id=segment, label=f"{humanize_key(field)}: {value}")
        return None


def _sum_row_counts(raw_calls: list[dict[str, Any]]) -> int:
    total = 0
    for row in raw_calls:
        value = row.get("row_count")
        if isinstance(value, int | float):
            total += int(value)
    return total


def _last_ingestion(raw_calls: list[dict[str, Any]]) -> str | None:
    timestamps = [str(row["ingestion_ts"]) for row in raw_calls if row.get("ingestion_ts")]
    return max(timestamps) if timestamps else None


def _sum_metric(records: list[NormalizedRecord], metric: str) -> float | None:
    values = [value for record in records if (value := record.metric(metric)) is not None]
    if not values:
        return None
    return round(sum(values), 2)


def _avg_metric(records: list[NormalizedRecord], metric: str) -> float | None:
    values = [value for record in records if (value := record.metric(metric)) is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _display_bucket(label: str) -> str:
    normalized = label.casefold()
    if "desktop" in normalized:
        return "Desktop"
    if "mobile" in normalized or "phone" in normalized or "app" in normalized:
        return "Mobile"
    return label


def _sort_value(value: Any) -> tuple[int, Any]:
    if value is None:
        return (0, 0)
    if isinstance(value, int | float):
        return (1, value)
    return (1, str(value).casefold())


def _error_sort_value(row: Any, sort: str) -> tuple[int, Any]:
    value = getattr(row, sort, None)
    return _sort_value(value)


def _matches_metric_state(value: float | None, state: str) -> bool:
    if value is None:
        return False
    has_value = value > 0
    return has_value if state in {"with_error", "converted"} else not has_value


def raw_call_files(store: ParquetStore, country: str) -> list[Path]:
    root = store.settings.parquet_dir / f"country={country}" / "raw_api_calls"
    return sorted(root.rglob("*.parquet")) if root.exists() else []
