from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from backend.app.auth.browser_cookies import BrowserCookieProvider
from backend.app.auth.session_store import secret_store
from backend.app.config.settings import Settings
from backend.app.ingestion.models import IngestionCreate, IngestionJob
from backend.app.ingestion.planner import IngestionChunk, plan_ingestion_chunks
from backend.app.ingestion.policy import build_ingestion_range
from backend.app.ingestion.progress import update_progress
from backend.app.observability.sanitizer import sanitize_error
from backend.app.quantum.config_store import QuantumConfigStore
from backend.app.quantum_dashboard.builder import build_derived_datasets
from backend.app.quantum_dashboard.capture import capture_quantum_dashboard_cards
from backend.app.quantum_dashboard.discovery import discover_dashboard_from_config
from backend.app.quantum_dashboard.regression import run_regression
from backend.app.storage.parquet_store import ParquetStore


class IngestionService:
    def __init__(
        self,
        settings: Settings,
        config_store: QuantumConfigStore,
        parquet_store: ParquetStore,
        cookie_provider: BrowserCookieProvider,
    ) -> None:
        self.settings = settings
        self.config_store = config_store
        self.parquet_store = parquet_store
        self.cookie_provider = cookie_provider
        self.jobs: dict[str, IngestionJob] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def start(self, request: IngestionCreate) -> IngestionJob:
        ingestion_id = str(uuid.uuid4())
        job = IngestionJob(
            ingestion_id=ingestion_id,
            country=request.country.value,
            status="pending",
            started_at=datetime.now(UTC),
        )
        self.jobs[ingestion_id] = job
        self._tasks[ingestion_id] = asyncio.create_task(self._run(job, request))
        return job

    def list(self) -> list[IngestionJob]:
        return sorted(self.jobs.values(), key=lambda job: job.started_at, reverse=True)

    def get(self, ingestion_id: str) -> IngestionJob | None:
        return self.jobs.get(ingestion_id)

    def cancel(self, ingestion_id: str) -> IngestionJob | None:
        task = self._tasks.get(ingestion_id)
        job = self.jobs.get(ingestion_id)
        if task and not task.done():
            task.cancel()
        if job and job.status not in {
            "completed",
            "completed_with_warnings",
            "failed",
            "failed_regression",
            "cancelled",
        }:
            job.status = "cancelled"
            job.finished_at = datetime.now(UTC)
        return job

    async def _run(self, job: IngestionJob, request: IngestionCreate) -> None:
        started = time.perf_counter()
        job.status = "planning_range"
        job.endpoint_current = "/analytics + /analytics/historical"
        config = self.config_store.read()
        try:
            ingestion_range = build_ingestion_range(
                self.parquet_store.latest_source_end(request.country.value),
                depth_days=config.ingestion_depth_days,
                incremental_reprocess_days=self.settings.quantum_incremental_reprocess_days,
            )
            country_config = config.required_country_config(request.country)
            discovery = discover_dashboard_from_config(
                settings=self.settings,
                country_config=country_config,
            )
            if not discovery.dashboard_id:
                raise RuntimeError(
                    f"Country {request.country.value} needs a resolvable dashboard ID."
                )
            if config.session_mode == "manual":
                manual_cookie = secret_store.get_manual_cookie()
                if not manual_cookie:
                    raise RuntimeError("Manual session mode needs a cookie in memory.")
                cookies = self.cookie_provider.from_manual_header(
                    manual_cookie, str(discovery.base_url)
                )
            else:
                cookies = self.cookie_provider.load(config.browser.value, str(discovery.base_url))
            chunks = plan_ingestion_chunks(
                ingestion_range,
                chunk_days=self.settings.quantum_ingestion_chunk_days,
            )
            covered_ranges = self.parquet_store.covered_source_ranges(request.country.value)
            chunks_to_capture = [
                chunk for chunk in chunks if not _is_chunk_covered(chunk, covered_ranges)
            ]
            job.planned_chunks = len(chunks)
            job.chunks = [
                {
                    **chunk.details(),
                    "index": index,
                    "status": "pending"
                    if chunk in chunks_to_capture
                    else "skipped_already_ingested",
                    "completed_at": None,
                }
                for index, chunk in enumerate(chunks, start=1)
            ]
            update_progress(
                job,
                status="planning_chunks",
                completed_chunks=len(chunks) - len(chunks_to_capture),
                message=(
                    f"Planificados {len(chunks)} chunks; "
                    f"{len(chunks_to_capture)} pendientes de captura."
                ),
            )
            rows: list[dict[str, Any]] = []
            chunk_indexes = {chunk: index for index, chunk in enumerate(chunks, start=1)}
            skipped_chunks = len(chunks) - len(chunks_to_capture)
            for capture_index, chunk in enumerate(chunks_to_capture, start=1):
                index = chunk_indexes[chunk]
                current_task = asyncio.current_task()
                if current_task is not None and current_task.cancelled():
                    raise asyncio.CancelledError
                job.current_chunk_index = index
                job.current_chunk_start = chunk.details()["start"]
                job.current_chunk_end = chunk.details()["end"]
                _set_chunk_status(job, index, "running")
                update_progress(
                    job,
                    status="capturing_chunk",
                    completed_chunks=skipped_chunks + capture_index - 1,
                    message=f"Capturando chunk {index}/{len(chunks)} {chunk.label}.",
                )
                chunk_range = ingestion_range.__class__(
                    mode=ingestion_range.mode,
                    start=chunk.start,
                    end=chunk.end,
                    latest_source_end=ingestion_range.latest_source_end,
                    lookback_days=ingestion_range.lookback_days,
                )
                captured = await asyncio.to_thread(
                    capture_quantum_dashboard_cards,
                    settings=self.settings,
                    cookies=cookies,
                    country=request.country.value,
                    base_url=discovery.base_url,
                    dashboard_id=discovery.dashboard_id,
                    team_id=discovery.team_id,
                    summary_tab=discovery.summary_tab,
                    errors_tab=discovery.errors_tab,
                    ingestion_id=job.ingestion_id,
                    ingestion_range=chunk_range,
                )
                rows.extend(captured)
                update_progress(
                    job,
                    completed_chunks=skipped_chunks + capture_index,
                    calls_captured=len(rows),
                    rows_captured=sum(int(row.get("row_count") or 0) for row in rows),
                    message=f"Chunk {index}/{len(chunks)} persistido en memoria.",
                )
                _set_chunk_status(job, index, "completed")
            update_progress(job, status="persisting_raw", message="Persistiendo RAW Parquet.")
            merge = (
                self.parquet_store.merge_raw_calls(request.country.value, rows) if rows else None
            )
            job.records_received = sum(int(row.get("row_count") or 0) for row in rows)
            job.records_persisted = merge.rows_captured if merge else 0
            job.calls_captured = len(rows)
            job.rows_captured = job.records_received
            job.pages_processed = 2
            update_progress(job, status="building_derived", message="Construyendo derivados.")
            build = build_derived_datasets(
                self.parquet_store,
                request.country.value,
                raw_calls=rows or None,
                ingestion_id=job.ingestion_id,
            )
            job.mandatory_cards_total = build.mandatory_cards
            job.mandatory_cards_captured = build.mandatory_cards_captured
            job.derived_datasets = build.derived_datasets
            update_progress(job, status="running_regression", message="Ejecutando regresion.")
            report = run_regression(
                self.parquet_store,
                request.country.value,
                ingestion_id=job.ingestion_id,
            )
            job.regression_status = report.status
            job.details = {
                "parquet_path": str(merge.path) if merge and merge.path else None,
                "raw_calls": len(rows),
                "rows_replaced": merge.rows_replaced if merge else 0,
                "rows_after_merge": merge.rows_after if merge else 0,
                "skipped_chunks": skipped_chunks,
                "captured_chunks": len(chunks_to_capture),
                "cards_captured": build.captured_cards,
                "mandatory_cards": build.mandatory_cards,
                "mandatory_cards_captured": build.mandatory_cards_captured,
                "derived_datasets": build.derived_datasets,
                "regression_status": report.status,
                "regression_verdict": report.verdict,
                "missing_roles": build.missing_roles,
                "parser_errors": build.parser_errors,
                "regression_report": "docs/regression/latest-web-vs-local.md",
                "range": ingestion_range.details(),
                "dashboard": discovery.model_dump(mode="json"),
            }
            if report.verdict == "FAILED":
                job.status = "failed_regression"
            elif build.missing_roles:
                job.status = "completed_with_warnings"
            else:
                job.status = "completed"
            update_progress(job, status=job.status, completed_chunks=job.planned_chunks)
        except asyncio.CancelledError:
            job.status = "cancelled"
            job.errors.append("Ingestion cancelled.")
        except Exception as exc:
            job.status = "failed"
            job.errors.append(sanitize_error(exc))
        finally:
            job.finished_at = datetime.now(UTC)
            job.duration_seconds = round(time.perf_counter() - started, 2)
            self.parquet_store.append_manifest(job.model_dump(mode="json"))


def _is_chunk_covered(
    chunk: IngestionChunk,
    covered_ranges: list[tuple[datetime, datetime]],
) -> bool:
    return any(
        range_start <= chunk.start and range_end >= chunk.end
        for range_start, range_end in covered_ranges
    )


def _set_chunk_status(job: IngestionJob, index: int, status: str) -> None:
    next_chunks = []
    for chunk in job.chunks:
        if int(chunk.get("index") or 0) == index:
            next_chunks.append(
                {
                    **chunk,
                    "status": status,
                    "completed_at": datetime.now(UTC).isoformat()
                    if status == "completed"
                    else chunk.get("completed_at"),
                }
            )
        else:
            next_chunks.append(chunk)
    job.chunks = next_chunks
