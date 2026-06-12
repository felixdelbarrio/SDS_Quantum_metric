from pathlib import Path

from backend.app.config.settings import Settings
from backend.app.storage.parquet_store import ParquetStore


def test_parquet_store_roundtrip(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    rows = [
        {
            "ingestion_id": "ing-1",
            "ingestion_ts": "2026-06-12T00:00:00Z",
            "country": "MX",
            "source_endpoint": "/analytics",
            "http_method": "POST",
            "status_code": 200,
            "dashboard_id": "dash",
            "card_id": "card",
            "card_type": "TABLE",
            "view_name": "topN",
            "metric_ids": "[]",
            "query_hash": "q",
            "response_hash": "r",
            "request_json": "{}",
            "response_json": '{"rows":[1,2]}',
            "row_count": 2,
            "source_ts_start": None,
            "source_ts_end": None,
        }
    ]

    path = store.write_raw_calls("MX", rows)
    store.append_manifest(
        {
            "ingestion_id": "ing-1",
            "country": "MX",
            "status": "completed",
            "started_at": "2026-06-12T00:00:00Z",
        }
    )

    assert path is not None and path.exists()
    assert store.list_datasets()[0]["country"] == "MX"
    assert store.analytics_summary()["raw_calls"] == 1
    assert store.card_data("card")[0]["view_name"] == "topN"
    assert store.list_ingestions()[0]["ingestion_id"] == "ing-1"
    exported = store.export_countries(["MX"])
    assert exported.exists()
    assert store.delete_country("MX") is True
    imported = store.import_zip(exported)
    assert imported["manifest"]["countries"] == ["MX"]
    assert store.list_datasets()[0]["country"] == "MX"
