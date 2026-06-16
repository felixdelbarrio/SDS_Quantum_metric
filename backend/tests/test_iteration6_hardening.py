from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.api.routes import config_store_dep, parquet_store_dep, settings_dep
from backend.app.config.paths import default_user_data_dir, frontend_dist_path
from backend.app.config.settings import Settings
from backend.app.ingestion.models import IngestionJob
from backend.app.ingestion.planner import plan_ingestion_chunks
from backend.app.ingestion.policy import IngestionRange, apply_ingestion_range
from backend.app.ingestion.progress import update_progress
from backend.app.ingestion.time_rewriter import (
    extract_query_time_range,
    rewrite_query_time_range,
)
from backend.app.main import create_app
from backend.app.quantum.config_store import QuantumConfigStore
from backend.app.quantum_dashboard.semantics import semantic_intent, semantic_state
from backend.app.storage.parquet_store import ParquetStore


def test_default_data_dir_is_user_persistent() -> None:
    assert default_user_data_dir().name == "SDS Quantum Metric"
    assert default_user_data_dir() != Path("data")


def test_frontend_dist_path_resolves_packaged_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id='root'></div>")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    path = frontend_dist_path()

    assert (path / "index.html").exists()


def test_spa_and_health_are_served(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dist = tmp_path / "bundle" / "frontend" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id='root'></div>")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
    settings = Settings(qm_data_dir=tmp_path / "data")
    app = create_app()
    app.dependency_overrides[settings_dep] = lambda: settings
    app.dependency_overrides[config_store_dep] = lambda: QuantumConfigStore(settings)
    app.dependency_overrides[parquet_store_dep] = lambda: ParquetStore(settings)
    client = TestClient(app)
    try:
        assert client.get("/api/health").json() == {"status": "ok"}
        assert "<!doctype html>" in client.get("/").text.lower()
    finally:
        app.dependency_overrides.clear()


def test_planner_chunks_backfill_by_day() -> None:
    end = datetime(2026, 6, 16, tzinfo=UTC)
    ingestion_range = IngestionRange(
        mode="backfill",
        start=end - timedelta(days=365),
        end=end,
        latest_source_end=None,
        lookback_days=365,
    )

    chunks = plan_ingestion_chunks(ingestion_range, chunk_days=1)

    assert len(chunks) == 365
    assert chunks[0].start == ingestion_range.start
    assert chunks[-1].end == ingestion_range.end


def test_planner_handles_empty_window_and_naive_datetimes() -> None:
    timestamp = datetime(2026, 6, 16, 12, 0)
    ingestion_range = IngestionRange(
        mode="incremental",
        start=timestamp,
        end=timestamp,
        latest_source_end=None,
    )

    chunks = plan_ingestion_chunks(ingestion_range, chunk_days=0)

    assert len(chunks) == 1
    assert chunks[0].details()["start"] == "2026-06-16T12:00:00Z"
    assert chunks[0].label == "2026-06-16"


def test_time_rewriter_handles_nested_predicates_and_metadata() -> None:
    chunk = plan_ingestion_chunks(
        IngestionRange(
            mode="incremental",
            start=datetime(2026, 6, 15, tzinfo=UTC),
            end=datetime(2026, 6, 16, tzinfo=UTC),
            latest_source_end=datetime(2026, 6, 15, tzinfo=UTC),
        )
    )[0]
    payload = {
        "query": {
            "metadata": {"baseTs": 1000, "endTs": 2000, "utcOffset": -21600},
            "filters": [
                {
                    "predicateFnNamespace": ["qm", "default", "predicates", "gte"],
                    "path": ["session", "ts"],
                    "arguments": [1000],
                },
                {
                    "predicateFnNamespace": ["qm", "default", "predicates", "lt"],
                    "path": ["session", "ts"],
                    "arguments": [2000],
                },
            ],
        }
    }

    result = rewrite_query_time_range(payload, chunk)
    extracted = extract_query_time_range(result.payload)

    assert result.changed is True
    assert extracted is not None
    assert extracted.start == chunk.start
    assert extracted.end == chunk.end


def test_time_rewriter_handles_quantum_arguments_path_predicates() -> None:
    chunk = plan_ingestion_chunks(
        IngestionRange(
            mode="incremental",
            start=datetime(2026, 6, 15, tzinfo=UTC),
            end=datetime(2026, 6, 16, tzinfo=UTC),
            latest_source_end=datetime(2026, 6, 15, tzinfo=UTC),
        )
    )[0]
    payload = {
        "query": {
            "filters": [
                {
                    "predicateFnNamespace": ["qm", "default", "predicates", "gte"],
                    "arguments": [
                        {"path": ["session", "ts"], "namespace": [], "metadata": {}},
                        1000,
                    ],
                },
                {
                    "predicateFnNamespace": ["qm", "default", "predicates", "lt"],
                    "arguments": [
                        {"path": ["session", "ts"], "namespace": [], "metadata": {}},
                        2000,
                    ],
                },
            ]
        }
    }

    result = rewrite_query_time_range(payload, chunk)
    extracted = extract_query_time_range(result.payload)

    assert result.changed is True
    assert result.payload["query"]["filters"][0]["arguments"][1] == 1781481600
    assert result.payload["query"]["filters"][1]["arguments"][1] == 1781568000
    assert extracted is not None
    assert extracted.start == chunk.start
    assert extracted.end == chunk.end


def test_time_rewriter_handles_top_level_window_string_epoch_and_offset() -> None:
    chunk = plan_ingestion_chunks(
        IngestionRange(
            mode="backfill",
            start=datetime(2026, 6, 14, tzinfo=UTC),
            end=datetime(2026, 6, 16, tzinfo=UTC),
            latest_source_end=None,
        ),
        chunk_days=2,
    )[0]
    payload = {
        "timezone": "CST",
        "period": "Today",
        "ts": ["1717200000000", "1717286400000"],
        "query": {"metadata": {"utcOffset": -18_000}},
    }

    result = rewrite_query_time_range(payload, chunk)
    extracted = extract_query_time_range(result.payload)

    assert result.payload["ts"] == ["1781395200000", "1781568000000"]
    assert extracted is not None
    assert extracted.timezone == "CST"
    assert extracted.label == "Today"


def test_apply_ingestion_range_uses_legacy_ts_fallback_without_query_rewriter_match() -> None:
    ingestion_range = IngestionRange(
        mode="incremental",
        start=datetime(2026, 6, 10, tzinfo=UTC),
        end=datetime(2026, 6, 11, tzinfo=UTC),
        latest_source_end=datetime(2026, 6, 9, tzinfo=UTC),
    )
    payload = {"filters": [{"name": "date", "ts": [1000.0, 2000.0]}]}

    rewritten, changed = apply_ingestion_range(payload, ingestion_range)

    assert changed is True
    assert rewritten["filters"][0]["ts"] == [
        datetime(2026, 6, 10, tzinfo=UTC).timestamp(),
        datetime(2026, 6, 11, tzinfo=UTC).timestamp(),
    ]


def test_update_progress_tracks_chunks_cards_and_tail_states() -> None:
    job = IngestionJob(
        ingestion_id="job-1",
        country="MX",
        status="planning_chunks",
        started_at=datetime(2026, 6, 16, tzinfo=UTC),
        planned_chunks=4,
        mandatory_cards_total=10,
    )

    update_progress(
        job,
        status="capturing_chunk",
        message="Capturando chunk",
        completed_chunks=2,
        calls_captured=12,
        rows_captured=120,
        mandatory_cards_captured=5,
        current_card_role="summary.sessions",
        current_tab="Resumen",
    )

    assert job.status == "capturing_chunk"
    assert job.records_persisted == 12
    assert job.records_received == 120
    assert job.progress_percent == 45
    assert job.last_progress_at is not None
    assert job.current_card_role == "summary.sessions"

    update_progress(job, status="completed", completed_chunks=4, mandatory_cards_captured=10)

    assert job.progress_percent == 100


def test_semantics_lower_is_good_and_higher_is_good() -> None:
    assert semantic_state("error_session_percent", 10) == "negative"
    assert semantic_intent("error_session_percent", -10) == "good"
    assert semantic_state("conversions", 10) == "positive"
    assert semantic_state("page_views", 10) == "neutral"


def test_dataset_entities_are_paged_and_delete_requires_confirm(tmp_path: Path) -> None:
    settings = Settings(qm_data_dir=tmp_path)
    store = ParquetStore(settings)
    store.merge_raw_calls(
        "MX",
        [
            {
                "country": "MX",
                "source_endpoint": "/analytics",
                "dashboard_id": "dash",
                "card_id": f"card-{index}",
                "card_type": "CHART",
                "view_name": "coreMetrics",
                "metric_ids": "[]",
                "query_hash": f"q-{index}",
                "response_hash": f"r-{index}",
                "source_ts_start": "2026-06-15T00:00:00Z",
                "source_ts_end": "2026-06-16T00:00:00Z",
                "row_count": 1,
            }
            for index in range(5)
        ],
    )
    app = create_app()
    app.dependency_overrides[settings_dep] = lambda: settings
    app.dependency_overrides[config_store_dep] = lambda: QuantumConfigStore(settings)
    app.dependency_overrides[parquet_store_dep] = lambda: store
    client = TestClient(app)
    try:
        entities = client.get("/api/datasets/MX/entities").json()
        page = client.get("/api/datasets/MX/entities/raw_api_calls?limit=2").json()
        rejected = client.delete("/api/datasets/MX")
    finally:
        app.dependency_overrides.clear()

    assert entities["entities"][0]["rows"] == 5
    assert page["total"] == 5
    assert len(page["rows"]) == 2
    assert rejected.status_code == 400


def test_delete_country_all_removes_parquet_and_ingestion_history(tmp_path: Path) -> None:
    settings = Settings(qm_data_dir=tmp_path)
    store = ParquetStore(settings)
    store.merge_raw_calls(
        "MX",
        [
            {
                "country": "MX",
                "source_endpoint": "/analytics",
                "dashboard_id": "dash",
                "card_id": "card",
                "card_type": "CHART",
                "view_name": "coreMetrics",
                "metric_ids": "[]",
                "query_hash": "q",
                "response_hash": "r",
                "source_ts_start": "2026-06-15T00:00:00Z",
                "source_ts_end": "2026-06-16T00:00:00Z",
                "row_count": 1,
            }
        ],
    )
    store.append_manifest(
        {
            "ingestion_id": "mx-1",
            "country": "MX",
            "status": "completed",
            "started_at": "2026-06-16T00:00:00Z",
        }
    )
    store.append_manifest(
        {
            "ingestion_id": "es-1",
            "country": "ES",
            "status": "completed",
            "started_at": "2026-06-16T00:00:00Z",
        }
    )
    settings.runtime_dir.mkdir(parents=True, exist_ok=True)
    settings.exports_dir.mkdir(parents=True, exist_ok=True)
    (settings.runtime_dir / "cache-MX.json").write_text("{}", encoding="utf-8")
    (settings.exports_dir / "quantum_export_MX_fixture.zip").write_bytes(b"zip")

    result = store.delete_country_all("MX", confirm="MX")

    assert result.status == "deleted"
    assert result.deleted_ingestions == 1
    assert result.deleted_files >= 3
    assert not (settings.parquet_dir / "country=MX").exists()
    assert not (settings.runtime_dir / "cache-MX.json").exists()
    assert not (settings.exports_dir / "quantum_export_MX_fixture.zip").exists()
    assert [row["ingestion_id"] for row in store.list_ingestions()] == ["es-1"]
