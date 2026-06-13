from __future__ import annotations

from typing import Any

from backend.app.analytics.models import SortDirection
from backend.app.analytics.query_engine import AnalyticsQueryEngine
from backend.app.storage.parquet_store import ParquetStore


class AnalyticsService:
    def __init__(self, store: ParquetStore) -> None:
        self.store = store
        self.engine = AnalyticsQueryEngine(store)

    def summary(self) -> dict[str, object]:
        return self.store.analytics_summary()

    def countries(self) -> dict[str, Any]:
        return self.engine.countries().model_dump(mode="json")

    def dashboard_summary(
        self,
        country: str,
        dimension: str | None = None,
        segment: str | None = None,
    ) -> dict[str, Any]:
        return self.engine.summary(country, dimension, segment).model_dump(mode="json")

    def dashboard_summary_table(
        self,
        country: str,
        search: str | None = None,
        sort: str = "page_views",
        direction: SortDirection = "desc",
        dimension: str | None = None,
        segment: str | None = None,
    ) -> dict[str, Any]:
        return self.engine.summary_table(
            country=country,
            search=search,
            sort=sort,
            direction=direction,
            dimension=dimension,
            segment=segment,
        ).model_dump(mode="json")

    def dashboard_errors(
        self,
        country: str,
        dimension: str | None = None,
        segment: str | None = None,
    ) -> dict[str, Any]:
        return self.engine.errors(country, dimension, segment).model_dump(mode="json")

    def dashboard_errors_table(
        self,
        country: str,
        search: str | None = None,
        sort: str = "error_session_percent",
        direction: SortDirection = "desc",
        dimension: str | None = None,
        segment: str | None = None,
    ) -> dict[str, Any]:
        return self.engine.errors_table(
            country=country,
            search=search,
            sort=sort,
            direction=direction,
            dimension=dimension,
            segment=segment,
        ).model_dump(mode="json")

    def dimensions(self, country: str) -> dict[str, Any]:
        return self.engine.dimensions(country).model_dump(mode="json")

    def segments(self, country: str) -> dict[str, Any]:
        return self.engine.segments(country).model_dump(mode="json")

    def timeseries(self) -> dict[str, object]:
        countries = self.engine.countries()
        dashboard = self.engine.summary(countries.default_country)
        page_views = next(
            (widget for widget in dashboard.widgets if widget.id == "page_views"),
            None,
        )
        return {
            "status": dashboard.status,
            "country": countries.default_country,
            "source": "parquet",
            "series": [point.model_dump(mode="json") for point in page_views.timeseries]
            if page_views
            else [],
            "reason": dashboard.reason,
        }

    def table(self) -> dict[str, object]:
        countries = self.engine.countries()
        return self.engine.summary_table(countries.default_country).model_dump(mode="json")

    def filters(self) -> dict[str, object]:
        countries = self.engine.countries()
        return {
            "filters": [
                {
                    "name": "country",
                    "source": "partition",
                    "values": [country.model_dump(mode="json") for country in countries.countries],
                }
            ]
        }
