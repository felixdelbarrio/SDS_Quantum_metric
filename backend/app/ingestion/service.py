from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime

from backend.app.auth.browser_cookies import BrowserCookieProvider
from backend.app.auth.session_store import secret_store
from backend.app.config.settings import Settings
from backend.app.ingestion.capture import capture_quantum_analytics
from backend.app.ingestion.models import IngestionCreate, IngestionJob
from backend.app.ingestion.policy import CAPTURE_WAIT_SECONDS, build_ingestion_range
from backend.app.observability.sanitizer import sanitize_error
from backend.app.quantum.config_store import QuantumConfigStore
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
            status="queued",
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
        if job and job.status in {"queued", "running"}:
            job.status = "cancelled"
            job.finished_at = datetime.now(UTC)
        return job

    async def _run(self, job: IngestionJob, request: IngestionCreate) -> None:
        started = time.perf_counter()
        job.status = "running"
        job.endpoint_current = "/analytics"
        config = self.config_store.read()
        dashboard_url = (
            request.dashboard_url or config.dashboard_url or self.settings.qm_default_dashboard_url
        )
        ingestion_range = build_ingestion_range(
            self.parquet_store.latest_source_end(request.country.value)
        )
        try:
            if config.session_mode == "manual":
                manual_cookie = secret_store.get_manual_cookie()
                if not manual_cookie:
                    raise RuntimeError("Manual session mode needs a cookie in memory.")
                cookies = self.cookie_provider.from_manual_header(
                    manual_cookie, str(config.base_url)
                )
            else:
                cookies = self.cookie_provider.load(config.browser.value, str(config.base_url))
            rows = await asyncio.to_thread(
                capture_quantum_analytics,
                settings=self.settings,
                cookies=cookies,
                country=request.country.value,
                dashboard_url=dashboard_url,
                wait_seconds=CAPTURE_WAIT_SECONDS,
                ingestion_id=job.ingestion_id,
                ingestion_range=ingestion_range,
            )
            merge = self.parquet_store.merge_raw_calls(request.country.value, rows)
            job.records_received = sum(int(row.get("row_count") or 0) for row in rows)
            job.records_persisted = merge.rows_captured
            job.pages_processed = 1
            job.details = {
                "parquet_path": str(merge.path) if merge.path else None,
                "raw_calls": len(rows),
                "rows_replaced": merge.rows_replaced,
                "rows_after_merge": merge.rows_after,
                "range": ingestion_range.details(),
            }
            job.status = "completed"
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
