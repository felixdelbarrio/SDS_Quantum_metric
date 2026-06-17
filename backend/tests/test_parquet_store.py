import json
import zipfile
from pathlib import Path

import pytest

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


def test_parquet_store_rejects_unsafe_import_paths(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path / "data"))
    zip_path = tmp_path / "unsafe.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps({"countries": ["MX"]}))
        archive.writestr("parquet/../country=MX/raw_api_calls/raw_api_calls.parquet", b"bad")

    with pytest.raises(ValueError, match="Unsafe ZIP path"):
        store.import_zip(zip_path)


def test_parquet_store_merge_replaces_overlap_and_tracks_latest_source_end(
    tmp_path: Path,
) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    older = _raw_call(
        ingestion_id="ing-1",
        card_id="old",
        source_ts_start="2026-05-01T00:00:00Z",
        source_ts_end="2026-05-31T23:59:59Z",
    )
    overlap = _raw_call(
        ingestion_id="ing-1",
        card_id="overlap-old",
        source_ts_start="2026-06-01T00:00:00Z",
        source_ts_end="2026-06-10T00:00:00Z",
    )
    store.merge_raw_calls("MX", [older, overlap])

    replacement = _raw_call(
        ingestion_id="ing-2",
        card_id="overlap-new",
        source_ts_start="2026-06-03T00:00:00Z",
        source_ts_end="2026-06-13T00:00:00Z",
    )
    result = store.merge_raw_calls("MX", [replacement, replacement])

    assert result.path is not None and result.path.exists()
    assert result.rows_replaced == 1
    assert result.rows_after == 2
    latest = store.latest_source_end("MX")
    assert latest is not None
    assert latest.isoformat() == "2026-06-13T00:00:00+00:00"
    rows = store.card_data("old") + store.card_data("overlap-new")
    assert {row["card_id"] for row in rows} == {"old", "overlap-new"}


def test_parquet_store_lists_merged_covered_source_ranges(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    store.merge_raw_calls(
        "MX",
        [
            _raw_call(
                ingestion_id="ing-1",
                card_id="day-1",
                source_ts_start="2026-06-15T00:00:00Z",
                source_ts_end="2026-06-16T00:00:00Z",
            ),
            _raw_call(
                ingestion_id="ing-1",
                card_id="day-2",
                source_ts_start="2026-06-16T00:00:00Z",
                source_ts_end="2026-06-17T00:00:00Z",
            ),
        ],
    )

    ranges = store.covered_source_ranges("MX")

    assert len(ranges) == 1
    assert ranges[0][0].isoformat() == "2026-06-15T00:00:00+00:00"
    assert ranges[0][1].isoformat() == "2026-06-17T00:00:00+00:00"


def _raw_call(
    *,
    ingestion_id: str,
    card_id: str,
    source_ts_start: str,
    source_ts_end: str,
) -> dict[str, object]:
    return {
        "ingestion_id": ingestion_id,
        "ingestion_ts": "2026-06-12T00:00:00Z",
        "country": "MX",
        "source_endpoint": "/analytics",
        "http_method": "POST",
        "status_code": 200,
        "dashboard_id": "dash",
        "card_id": card_id,
        "card_type": "TABLE",
        "view_name": "topN",
        "metric_ids": "[]",
        "query_hash": f"q-{card_id}",
        "response_hash": f"r-{card_id}",
        "request_json": "{}",
        "response_json": '{"rows":[1]}',
        "row_count": 1,
        "source_ts_start": source_ts_start,
        "source_ts_end": source_ts_end,
    }
