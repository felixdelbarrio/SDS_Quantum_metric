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
from backend.app.ingestion.planner import plan_ingestion_chunks
from backend.app.ingestion.policy import build_ingestion_range
from backend.app.ingestion.progress import update_progress
from backend.app.observability.sanitizer import sanitize_error
from backend.app.quantum.config_store import QuantumConfigStore
from backend.app.quantum_dashboard.builder import build_derived_datasets
from backend.app.quantum_dashboard.capture import capture_quantum_dashboard_cards
from backend.app.quantum_dashboard.discovery import discover_dashboard_from_config
from backend.app.quantum_dashboard.regression import run_regression
from backend.app.storage.parquet_store import ParquetStore

TERMINAL_STATUSES = {
    "completed",
    "completed_with_warnings",
    "failed",
    "failed_regression",
    "cancelled",
}


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
            is_active=True,
        )
        self.jobs[ingestion_id] = job
        self._tasks[ingestion_id] = asyncio.create_task(self._run(job, request))
        return job

    def list_jobs(self) -> list[IngestionJob]:
        return sorted(self.jobs.values(), key=lambda job: job.started_at, reverse=True)

    def list_payload(self) -> dict[str, list[dict[str, Any]]]:
        active_jobs = [job for job in self.jobs.values() if _is_active(job)]
        memory_history = [job for job in self.jobs.values() if not _is_active(job)]
        persisted_history = self.parquet_store.list_ingestions()
        active = [_job_payload(job, is_active=True) for job in active_jobs]
        history_by_id: dict[str, dict[str, Any]] = {
            str(row.get("ingestion_id")): _manifest_payload(row) for row in persisted_history
        }
        for job in memory_history:
            history_by_id[job.ingestion_id] = _job_payload(job, is_active=False)
        history = sorted(
            history_by_id.values(),
            key=lambda row: str(row.get("started_at") or ""),
            reverse=True,
        )
        active = sorted(active, key=lambda row: str(row.get("started_at") or ""), reverse=True)
        return {
            "active": active,
            "history": history,
        }

    def get(self, ingestion_id: str) -> IngestionJob | None:
        return self.jobs.get(ingestion_id)

    def cancel(self, ingestion_id: str) -> IngestionJob | None:
        task = self._tasks.get(ingestion_id)
        job = self.jobs.get(ingestion_id)
        if task and not task.done():
            task.cancel()
        if job and job.status not in TERMINAL_STATUSES:
            job.status = "cancelled"
            job.finished_at = datetime.now(UTC)
            job.is_active = False
        return job

    def purge_country(self, country: str) -> int:
        removed = 0
        for ingestion_id, job in list(self.jobs.items()):
            if job.country != country:
                continue
            task = self._tasks.pop(ingestion_id, None)
            if task and not task.done():
                task.cancel()
            self.jobs.pop(ingestion_id, None)
            removed += 1
        return removed

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
            job.planned_chunks = len(chunks)
            job.chunks = [
                {
                    **chunk.details(),
                    "index": index,
                    "status": "pending",
                    "completed_at": None,
                }
                for index, chunk in enumerate(chunks, start=1)
            ]
            update_progress(
                job,
                status="planning_chunks",
                message=f"Planificados {len(chunks)} chunks.",
            )
            rows: list[dict[str, Any]] = []
            for index, chunk in enumerate(chunks, start=1):
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
                    completed_chunks=index - 1,
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
                    completed_chunks=index,
                    calls_captured=len(rows),
                    rows_captured=sum(int(row.get("row_count") or 0) for row in rows),
                    message=f"Chunk {index}/{len(chunks)} persistido en memoria.",
                )
                _set_chunk_status(job, index, "completed")
            update_progress(job, status="persisting_raw", message="Persistiendo RAW Parquet.")
            merge = self.parquet_store.merge_raw_calls(request.country.value, rows)
            job.records_received = sum(int(row.get("row_count") or 0) for row in rows)
            job.records_persisted = merge.rows_captured
            job.calls_captured = len(rows)
            job.rows_captured = job.records_received
            job.pages_processed = 2
            update_progress(job, status="building_derived", message="Construyendo derivados.")
            build = build_derived_datasets(
                self.parquet_store,
                request.country.value,
                raw_calls=rows,
                ingestion_id=job.ingestion_id,
            )
            job.mandatory_cards_total = build.mandatory_cards
            job.mandatory_cards_captured = build.mandatory_cards_captured
            job.derived_datasets = build.derived_datasets
            update_progress(
                job,
                status="running_regression",
                message="Ejecutando regresion Today y ultimos 7 dias.",
            )
            today_report = run_regression(
                self.parquet_store,
                request.country.value,
                ingestion_id=job.ingestion_id,
                range_key="today",
                report_slug="today-web-vs-local",
            )
            last_7_days_report = run_regression(
                self.parquet_store,
                request.country.value,
                ingestion_id=job.ingestion_id,
                range_key="last_7_days",
                report_slug="last-7-days-web-vs-local",
            )
            regression_reports = {
                "today": today_report.model_dump(mode="json"),
                "last_7_days": last_7_days_report.model_dump(mode="json"),
            }
            failed_reports = [
                report
                for report in (today_report, last_7_days_report)
                if report.verdict == "FAILED"
            ]
            report = failed_reports[0] if failed_reports else today_report
            job.regression_status = report.status
            job.details = {
                "parquet_path": str(merge.path) if merge.path else None,
                "raw_calls": len(rows),
                "rows_replaced": merge.rows_replaced,
                "rows_after_merge": merge.rows_after,
                "cards_captured": build.captured_cards,
                "mandatory_cards": build.mandatory_cards,
                "mandatory_cards_captured": build.mandatory_cards_captured,
                "derived_datasets": build.derived_datasets,
                "regression_status": report.status,
                "regression_verdict": report.verdict,
                "regression_reports": regression_reports,
                "missing_roles": build.missing_roles,
                "parser_errors": build.parser_errors,
                "regression_report": "docs/regression/today-web-vs-local.md",
                "last_7_days_regression_report": "docs/regression/last-7-days-web-vs-local.md",
                "range": ingestion_range.details(),
                "dashboard": discovery.model_dump(mode="json"),
            }
            if failed_reports:
                job.status = "failed_regression"
            elif build.missing_roles:
                job.status = "failed_regression"
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
            job.is_active = False
            job.sort_index = job.started_at.isoformat()
            job.duration_seconds = round(time.perf_counter() - started, 2)
            self.parquet_store.append_manifest(job.model_dump(mode="json"))


def _is_active(job: IngestionJob) -> bool:
    return job.status not in TERMINAL_STATUSES


def _job_payload(job: IngestionJob, *, is_active: bool) -> dict[str, Any]:
    payload = job.model_dump(mode="json")
    payload["is_active"] = is_active
    payload["sort_index"] = payload.get("started_at")
    payload["chunks"] = sorted(
        _list_of_dicts(payload.get("chunks")),
        key=lambda chunk: str(chunk.get("start") or ""),
    )
    return payload


def _manifest_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload["is_active"] = False
    payload["sort_index"] = payload.get("started_at")
    payload["chunks"] = sorted(
        _list_of_dicts(payload.get("chunks")),
        key=lambda chunk: str(chunk.get("start") or ""),
    )
    return payload


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


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
