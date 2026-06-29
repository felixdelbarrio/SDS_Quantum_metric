from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.api.routes import config_store_dep, parquet_store_dep, settings_dep
from backend.app.config.paths import default_user_data_dir, frontend_dist_path
from backend.app.config.settings import Settings
from backend.app.ingestion.capture import (
    _configure_playwright_browser_path,
    _effective_source_end,
    _launch_headless_browser,
)
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
from backend.app.runtime import API_SCHEMA_VERSION, APP_ID
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
        health = client.get("/api/health").json()
        assert health["status"] == "ok"
        assert health["app"] == APP_ID
        assert health["api_schema"] == API_SCHEMA_VERSION
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
    assert chunks[0].end == ingestion_range.end
    assert chunks[-1].start == ingestion_range.start
    assert chunks[0].start > chunks[-1].start


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


def test_time_rewriter_handles_hit_ts_predicates_and_dimension_fills() -> None:
    chunk = plan_ingestion_chunks(
        IngestionRange(
            mode="backfill",
            start=datetime(2026, 6, 23, 6, tzinfo=UTC),
            end=datetime(2026, 6, 30, 5, 59, 59, tzinfo=UTC),
            latest_source_end=None,
        ),
        chunk_days=7,
    )[0]
    payload = {
        "dimensionFills": {
            "dimensionFills": [
                {"arguments": [1782712800, 1782719880, 60, -21600]},
            ]
        },
        "filter": {
            "predicateFnNamespace": ["qm", "default", "predicates", "and"],
            "arguments": [
                {
                    "predicateFnNamespace": ["qm", "default", "predicates", "gte"],
                    "arguments": [{"path": ["hit", "ts"]}, 1782712800],
                },
                {
                    "predicateFnNamespace": ["qm", "default", "predicates", "lt"],
                    "arguments": [{"path": ["hit", "ts"]}, 1782719940],
                },
            ],
        },
    }

    result = rewrite_query_time_range(payload, chunk)
    extracted = extract_query_time_range(result.payload)

    assert result.changed is True
    assert extracted is not None
    assert extracted.start == chunk.start
    assert extracted.end == chunk.end
    assert result.payload["dimensionFills"]["dimensionFills"][0]["arguments"][:2] == [
        int(chunk.start.timestamp()),
        int(chunk.end.timestamp()),
    ]


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


def test_capture_effective_end_uses_complete_archive_hour() -> None:
    requested_end = datetime(2026, 6, 30, 5, 59, 59, tzinfo=UTC)
    archive_cutoff = datetime(2026, 6, 29, 10, 44, 34, tzinfo=UTC).timestamp()

    end = _effective_source_end(requested_end, {"stats": {"archive_cutoff_ts": archive_cutoff}})

    assert end == datetime(2026, 6, 29, 9, 59, 59, tzinfo=UTC)


def test_capture_prefers_playwright_chromium_over_user_chrome(tmp_path: Path) -> None:
    settings = Settings(qm_data_dir=tmp_path)
    chromium = _FakeChromium()
    playwright = type("Playwright", (), {"chromium": chromium})()

    _launch_headless_browser(playwright, settings)

    assert chromium.calls[0]["executable_path"] is None


def test_capture_does_not_fall_back_to_user_chrome_when_playwright_browser_missing(
    tmp_path: Path,
) -> None:
    settings = Settings(qm_data_dir=tmp_path)
    chromium = _FakeChromium(fail_first=True)
    playwright = type("Playwright", (), {"chromium": chromium})()

    with pytest.raises(RuntimeError, match="Playwright Chromium is not available"):
        _launch_headless_browser(playwright, settings)

    assert chromium.calls[0]["executable_path"] is None
    assert len(chromium.calls) == 1


def test_packaged_capture_uses_bundled_playwright_browsers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_root = tmp_path / "playwright"
    browser_root = package_root / "driver" / "package" / ".local-browsers" / "chromium-1"
    browser_root.mkdir(parents=True)
    module = type("PlaywrightModule", (), {"__file__": str(package_root / "__init__.py")})()
    monkeypatch.setitem(sys.modules, "playwright", module)
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)

    _configure_playwright_browser_path()

    assert "PLAYWRIGHT_BROWSERS_PATH" in os.environ
    assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == "0"


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


def test_update_progress_shows_activity_while_capturing_tabs() -> None:
    job = IngestionJob(
        ingestion_id="job-1",
        country="MX",
        status="capturing_chunk",
        started_at=datetime(2026, 6, 16, tzinfo=UTC),
        planned_chunks=1,
        mandatory_cards_total=9,
    )

    update_progress(job, status="capturing_summary_tab", current_tab="Resumen")
    summary_progress = job.progress_percent
    update_progress(job, status="capturing_errors_tab", current_tab="Errores")

    assert summary_progress > 0
    assert job.progress_percent > summary_progress
    assert job.current_tab == "Errores"


def test_semantics_lower_is_good_and_higher_is_good() -> None:
    assert semantic_state("error_session_percent", 10) == "negative"
    assert semantic_intent("error_session_percent", -10) == "good"
    assert semantic_state("conversions", 10) == "positive"
    assert semantic_state("page_views", 10) == "neutral"


class _FakeChromium:
    def __init__(self, *, fail_first: bool = False) -> None:
        self.fail_first = fail_first
        self.calls: list[dict[str, object | None]] = []

    def launch(self, **kwargs: object) -> object:
        self.calls.append(
            {
                "executable_path": kwargs.get("executable_path"),
                "headless": kwargs.get("headless"),
            }
        )
        if self.fail_first and len(self.calls) == 1:
            raise RuntimeError("missing playwright chromium")
        return object()


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
