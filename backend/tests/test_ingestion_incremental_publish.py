from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from backend.app.auth.browser_cookies import BrowserCookieProvider
from backend.app.config.settings import Settings
from backend.app.ingestion.models import IngestionCreate, IngestionJob
from backend.app.ingestion.planner import IngestionChunk
from backend.app.ingestion.policy import IngestionRange
from backend.app.ingestion.service import IngestionService
from backend.app.quantum.config_store import QuantumConfigStore
from backend.app.quantum.schemas import Country, QuantumConfig
from backend.app.quantum_dashboard.models import DashboardDiscoveryResult
from backend.app.storage.parquet_store import ParquetStore, RawCallMergeResult


@pytest.mark.asyncio
async def test_ingestion_publishes_dashboard_after_each_completed_chunk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(qm_data_dir=tmp_path)
    store = ParquetStore(settings)
    service = IngestionService(
        settings,
        _ConfigStore(settings),
        store,
        cast(BrowserCookieProvider, _CookieProvider()),
    )
    now = datetime(2026, 6, 17, tzinfo=UTC)
    chunks = [
        IngestionChunk(now - timedelta(days=1), now, "2026-06-16 -> 2026-06-17"),
        IngestionChunk(
            now - timedelta(days=2), now - timedelta(days=1), "2026-06-15 -> 2026-06-16"
        ),
    ]
    published_chunks: list[list[dict[str, Any]]] = []

    def fake_capture(**kwargs: Any) -> list[dict[str, Any]]:
        ingestion_range = kwargs["ingestion_range"]
        return [
            {
                "row_count": 10,
                "capture_chunk_start": ingestion_range.start.isoformat(),
                "capture_chunk_end": ingestion_range.end.isoformat(),
            }
        ]

    def fake_publish(
        parquet_store: ParquetStore,
        country: str,
        rows: list[dict[str, Any]],
        ingestion_id: str,
        enabled_roles: set[str],
    ) -> tuple[RawCallMergeResult, _Build, _Report]:
        assert "summary.page_views" in enabled_roles
        published_chunks.append(rows)
        return (
            RawCallMergeResult(
                path=None,
                rows_captured=len(rows),
                rows_replaced=0,
                rows_after=len(published_chunks),
            ),
            _Build(),
            _Report(),
        )

    monkeypatch.setattr(
        "backend.app.ingestion.service.build_ingestion_range",
        lambda *args, **kwargs: IngestionRange(
            "backfill", chunks[-1].start, chunks[0].end, None, 2
        ),
    )
    monkeypatch.setattr(
        "backend.app.ingestion.service.plan_ingestion_chunks", lambda *args, **kwargs: chunks
    )
    monkeypatch.setattr(
        "backend.app.ingestion.service.discover_dashboard_from_config",
        lambda **kwargs: DashboardDiscoveryResult(
            country="MX",
            base_url="https://bbvamx.quantummetric.com",
            dashboard_id="dash",
            team_id="team",
            summary_tab=0,
            errors_tab=1,
            tabs=[],
            source="env",
            message="ok",
        ),
    )
    monkeypatch.setattr(
        "backend.app.ingestion.service.capture_quantum_dashboard_cards", fake_capture
    )
    monkeypatch.setattr("backend.app.ingestion.service._publish_completed_chunk", fake_publish)

    job = IngestionJob(
        ingestion_id="ingestion-id",
        country="MX",
        status="pending",
        started_at=now,
    )

    await service._run(job, IngestionCreate(country=Country.MX))

    assert job.status == "completed"
    assert len(published_chunks) == 2
    assert [chunk["status"] for chunk in job.chunks] == ["completed", "completed"]
    assert job.records_persisted == 2
    assert job.progress_percent == 100


@pytest.mark.asyncio
async def test_ingestion_fails_when_capture_returns_no_analytics_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(qm_data_dir=tmp_path)
    store = ParquetStore(settings)
    service = IngestionService(
        settings,
        _ConfigStore(settings),
        store,
        cast(BrowserCookieProvider, _CookieProvider()),
    )
    now = datetime(2026, 6, 17, tzinfo=UTC)
    chunk = IngestionChunk(now - timedelta(days=1), now, "2026-06-16 -> 2026-06-17")

    monkeypatch.setattr(
        "backend.app.ingestion.service.build_ingestion_range",
        lambda *args, **kwargs: IngestionRange("backfill", chunk.start, chunk.end, None, 1),
    )
    monkeypatch.setattr(
        "backend.app.ingestion.service.plan_ingestion_chunks", lambda *args, **kwargs: [chunk]
    )
    monkeypatch.setattr(
        "backend.app.ingestion.service.discover_dashboard_from_config",
        lambda **kwargs: DashboardDiscoveryResult(
            country="MX",
            base_url="https://bbvamx.quantummetric.com",
            dashboard_id="dash",
            team_id="team",
            summary_tab=0,
            errors_tab=1,
            tabs=[],
            source="env",
            message="ok",
        ),
    )
    monkeypatch.setattr(
        "backend.app.ingestion.service.capture_quantum_dashboard_cards", lambda **kwargs: []
    )

    job = IngestionJob(
        ingestion_id="ingestion-id",
        country="MX",
        status="pending",
        started_at=now,
    )

    await service._run(job, IngestionCreate(country=Country.MX))

    assert job.status == "failed"
    assert any("No Quantum analytics responses" in error for error in job.errors)
    assert job.calls_captured == 0


class _ConfigStore(QuantumConfigStore):
    def read(self) -> QuantumConfig:
        return self.default()


class _CookieProvider:
    def load(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        return []


class _Build:
    mandatory_cards = 9
    mandatory_cards_captured = 9
    derived_datasets = 7
    captured_cards = 9
    missing_roles: list[str] = []
    parser_errors: list[dict[str, str]] = []


class _Report:
    status = "passed"
    verdict = "PASSED"
