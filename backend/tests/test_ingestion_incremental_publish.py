from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from backend.app.auth.browser_cookies import BrowserCookieProvider
from backend.app.config.settings import Settings
from backend.app.ingestion.models import IngestionCreate, IngestionJob
from backend.app.ingestion.planner import IngestionChunk
from backend.app.ingestion.policy import IngestionRange
from backend.app.ingestion.service import (
    IngestionAlreadyRunning,
    IngestionService,
    _filter_enabled_rows,
)
from backend.app.quantum.config_store import QuantumConfigStore
from backend.app.quantum.schemas import (
    Country,
    QuantumConfig,
    QuantumCountryConfig,
    QuantumDashboardConfig,
    QuantumWidgetConfig,
)
from backend.app.quantum_dashboard.models import DashboardDiscoveryResult
from backend.app.quantum_dashboard.range_query import RangeResolution
from backend.app.storage.parquet_store import ParquetStore, RawCallMergeResult


@pytest.mark.asyncio
async def test_ingestion_start_blocks_duplicate_active_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(qm_data_dir=tmp_path)
    service = IngestionService(
        settings,
        _ConfigStore(settings),
        ParquetStore(settings),
        cast(BrowserCookieProvider, _CookieProvider(cookies=["chrome-session"])),
    )
    started = asyncio.Event()

    async def hold_job(_job: IngestionJob, _request: IngestionCreate) -> None:
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(service, "_run", hold_job)
    request = IngestionCreate(
        country=Country.MX,
        range_key="last_7_days",
        start_date="2026-06-11",
        end_date="2026-06-17",
    )

    job = service.start(request)
    await started.wait()

    with pytest.raises(IngestionAlreadyRunning) as exc:
        service.start(request)

    assert exc.value.ingestion_id == job.ingestion_id
    service.cancel(job.ingestion_id)
    task = service._tasks[job.ingestion_id]
    with suppress(asyncio.CancelledError):
        await task


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
        cast(BrowserCookieProvider, _CookieProvider(cookies=["chrome-session"])),
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
        assert kwargs["session_mode"] == "browser"
        assert kwargs["cookies"] == ["chrome-session"]
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
        dashboard_id: str | None = None,
        dashboard_name: str | None = None,
        range_key: str | None = None,
        widget_configs: list[Any] | None = None,
    ) -> tuple[RawCallMergeResult, _Build, _Report]:
        _ = parquet_store, country, ingestion_id, dashboard_name, range_key
        assert "summary.page_views" in enabled_roles
        assert dashboard_id == "dash"
        assert widget_configs is not None
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
    monkeypatch.setattr(
        "backend.app.ingestion.service.resolve_range",
        lambda *args, **kwargs: RangeResolution(
            country="MX",
            range_key=str(kwargs.get("range_key") or "today"),
            start=chunks[-1].start,
            end=chunks[0].end,
            timezone="CST",
            required_days=[date(2026, 6, 16), date(2026, 6, 17)],
            covered_days=[date(2026, 6, 16), date(2026, 6, 17)],
            missing_days=[],
            completeness="complete",
            data_quality="complete",
            warning_level="none",
            last_regression_status="passed",
            message="Periodo completo en Parquet.",
        ),
    )

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

    assert job.status == "failed_no_analytics_responses"
    assert any("No Quantum analytics responses" in error for error in job.errors)
    assert job.calls_captured == 0


def test_filter_enabled_rows_materializes_resolved_card_role() -> None:
    rows = [
        {
            "tab": "summary",
            "card_id": "summary-card",
            "card_type": "CHART",
            "metric_ids": '["bde22d61-91c0-4d27-8ee3-ef467daea00c"]',
            "request_json": "{}",
        },
        {
            "tab": "summary",
            "card_id": "summary-card",
            "card_type": "CHART",
            "metric_ids": "[]",
            "request_json": "{}",
        },
    ]

    filtered = _filter_enabled_rows(rows, {"summary.page_views"})

    assert [row.get("card_role") for row in filtered] == [
        "summary.page_views",
        "summary.page_views",
    ]


def test_filter_enabled_rows_does_not_assign_ambiguous_tables_by_order() -> None:
    widgets = [
        QuantumWidgetConfig(
            role="generic.0.table.first",
            title="First table",
            widget_id="first-widget",
            card_id="shared-card",
            widget_type="TABLE",
            tab="summary",
            tab_index=0,
            enabled=True,
            supported=True,
        ),
        QuantumWidgetConfig(
            role="generic.0.table.second",
            title="Second table",
            widget_id="second-widget",
            card_id="shared-card",
            widget_type="TABLE",
            tab="summary",
            tab_index=0,
            enabled=True,
            supported=True,
        ),
    ]
    rows = [
        {
            "card_id": "shared-card",
            "card_type": "TABLE",
            "view_name": "table",
            "response_json": "{}",
        },
        {
            "card_id": "shared-card",
            "card_type": "TABLE",
            "view_name": "table",
            "response_json": "{}",
        },
    ]

    filtered = _filter_enabled_rows(
        rows,
        {"generic.0.table.first", "generic.0.table.second"},
        widgets,
    )

    assert len(filtered) == 2
    assert all("card_role" not in row for row in filtered)


class _ConfigStore(QuantumConfigStore):
    def read(self) -> QuantumConfig:
        return self.default().model_copy(
            update={
                "country": Country.MX,
                "countries": [
                    QuantumCountryConfig(
                        country=Country.MX,
                        base_url="https://bbvamx.quantummetric.com",
                        dashboard_id="dash",
                        team_id="team",
                        tab=0,
                        dashboards=[
                            QuantumDashboardConfig(
                                dashboard_id="dash",
                                name="Dashboard MX",
                                team_id="team",
                                summary_tab=0,
                                errors_tab=1,
                                is_default=True,
                                validated=True,
                                validation_status="ok",
                                widgets=[
                                    QuantumWidgetConfig(
                                        role="summary.page_views",
                                        title="Paginas vistas",
                                        widget_id="card-page-views",
                                        card_id="card-page-views",
                                        widget_type="CHART",
                                        tab="summary",
                                        tab_name="Resumen",
                                        tab_index=0,
                                        enabled=True,
                                        required=True,
                                        supported=True,
                                        source="quantum_web",
                                    )
                                ],
                            )
                        ],
                    )
                ],
            }
        )


class _CookieProvider:
    def __init__(self, cookies: list[str] | None = None) -> None:
        self.cookies = cookies or []

    def load(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self.cookies)


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
