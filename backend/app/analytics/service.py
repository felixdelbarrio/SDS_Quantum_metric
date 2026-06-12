from __future__ import annotations

from backend.app.storage.parquet_store import ParquetStore


class AnalyticsService:
    def __init__(self, store: ParquetStore) -> None:
        self.store = store

    def summary(self) -> dict[str, object]:
        return self.store.analytics_summary()

    def timeseries(self) -> dict[str, object]:
        return {"series": [], "source": "parquet", "note": "Derived timeseries parser pending."}

    def table(self) -> dict[str, object]:
        return {"rows": [], "source": "parquet", "note": "Derived table parser pending."}

    def filters(self) -> dict[str, object]:
        return {"filters": [{"name": "country", "source": "partition"}]}
