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


def test_delete_country_removes_parquet_and_ingestion_history(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    store.merge_raw_calls(
        "MX",
        [
            _raw_call(
                ingestion_id="mx-ing",
                card_id="mx-card",
                source_ts_start="2026-06-18T06:00:00Z",
                source_ts_end="2026-06-19T05:59:59Z",
            )
        ],
    )
    store.append_manifest(
        {
            "ingestion_id": "mx-ing",
            "country": "MX",
            "status": "failed",
            "started_at": "2026-06-18T20:00:00Z",
        }
    )
    store.append_manifest(
        {
            "ingestion_id": "es-ing",
            "country": "ES",
            "status": "completed",
            "started_at": "2026-06-18T19:00:00Z",
        }
    )

    assert store.delete_country("MX") is True

    assert store.list_datasets() == []
    assert [row["ingestion_id"] for row in store.list_ingestions()] == ["es-ing"]


def test_delete_country_clears_orphan_history_without_parquet(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    store.append_manifest(
        {
            "ingestion_id": "mx-orphan",
            "country": "MX",
            "status": "failed",
            "started_at": "2026-06-18T20:00:00Z",
        }
    )

    assert store.delete_country("MX") is True
    assert store.list_ingestions() == []


def test_parquet_store_rejects_unsafe_import_paths(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path / "data"))
    zip_path = tmp_path / "unsafe.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps({"countries": ["MX"]}))
        archive.writestr("parquet/../country=MX/raw_api_calls/raw_api_calls.parquet", b"bad")

    with pytest.raises(ValueError, match="Unsafe ZIP path"):
        store.import_zip(zip_path)


def test_parquet_store_export_import_includes_quantum_config(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path / "source"))
    store.settings.config_dir.mkdir(parents=True, exist_ok=True)
    store.settings.config_dir.joinpath("quantum.json").write_text(
        json.dumps(
            {
                "browser": "chrome",
                "session_mode": "browser",
                "country": "MX",
                "countries": [
                    {
                        "country": "MX",
                        "base_url": "https://bbvamx.quantummetric.com",
                        "dashboard_id": "dash",
                        "team_id": "team",
                        "tab": 0,
                        "enabled": True,
                    }
                ],
            }
        )
    )

    exported = store.export_countries(["MX"])
    with zipfile.ZipFile(exported) as archive:
        assert "config/quantum_config.json" in archive.namelist()
        assert "Cookie" not in archive.read("config/quantum_config.json").decode()

    target = ParquetStore(Settings(qm_data_dir=tmp_path / "target"))
    imported = target.import_zip(exported)

    assert imported["imported_files"] == 1
    assert (target.settings.config_dir / "quantum_config.json").exists()


def test_parquet_store_recovers_from_corrupt_manifest(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    manifest_path = store.settings.manifests_dir / "ingestion_manifest.parquet"
    manifest_path.write_bytes(b"bad")

    assert store.list_ingestions() == []

    store.append_manifest(
        {
            "ingestion_id": "ing-2",
            "country": "MX",
            "status": "completed",
            "started_at": "2026-06-12T00:00:00Z",
        }
    )

    assert store.list_ingestions()[0]["ingestion_id"] == "ing-2"
    assert list(store.settings.manifests_dir.glob("ingestion_manifest.corrupt-*.parquet"))


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


def test_parquet_store_merge_uses_capture_chunk_range_when_source_range_missing(
    tmp_path: Path,
) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    old = {
        **_raw_call(
            ingestion_id="ing-1",
            card_id="old-capture-range",
            source_ts_start="",
            source_ts_end="",
        ),
        "capture_chunk_start": "2026-06-18T06:00:00Z",
        "capture_chunk_end": "2026-06-19T05:59:59Z",
    }
    store.merge_raw_calls("MX", [old])
    replacement = {
        **_raw_call(
            ingestion_id="ing-2",
            card_id="new-capture-range",
            source_ts_start="",
            source_ts_end="",
        ),
        "capture_chunk_start": "2026-06-18T06:00:00Z",
        "capture_chunk_end": "2026-06-19T05:59:59Z",
    }

    result = store.merge_raw_calls("MX", [replacement])

    assert result.rows_replaced == 1
    assert result.rows_after == 1
    latest = store.latest_source_end("MX")
    assert latest is not None
    assert latest.isoformat() == "2026-06-19T05:59:59+00:00"
    assert store.card_data("new-capture-range")[0]["card_id"] == "new-capture-range"


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


def test_parquet_store_writes_daily_partitions_and_day_coverage(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    store.merge_raw_calls(
        "MX",
        [
            _raw_call(
                ingestion_id="ing-1",
                card_id="mx-day-15",
                source_ts_start="2026-06-15T06:00:00Z",
                source_ts_end="2026-06-16T05:59:59Z",
            ),
            _raw_call(
                ingestion_id="ing-1",
                card_id="mx-day-17",
                source_ts_start="2026-06-17T06:00:00Z",
                source_ts_end="2026-06-18T05:59:59Z",
            ),
        ],
    )

    root = tmp_path / "parquet" / "country=MX"

    assert (root / "day=2026-06-15" / "raw_api_calls" / "raw_api_calls.parquet").exists()
    assert (root / "manifests" / "day_coverage.parquet").exists()
    assert store.day_coverage("MX", "2026-06-15", "2026-06-17") == {
        "country": "MX",
        "start": "2026-06-15",
        "end": "2026-06-17",
        "complete": False,
        "covered_days": ["2026-06-15", "2026-06-17"],
        "missing_days": ["2026-06-16"],
        "message": "Falta 1 dia para completar el periodo: 2026-06-16.",
    }


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
