from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime

from backend.app.auth.browser_cookies import BrowserCookieProvider
from backend.app.auth.session_store import secret_store
from backend.app.config.settings import Settings
from backend.app.ingestion.models import IngestionCreate, IngestionJob
from backend.app.ingestion.policy import build_ingestion_range
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
        job.status = "running"
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
            job.status = "planning_range"
            rows = await asyncio.to_thread(
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
                ingestion_range=ingestion_range,
            )
            job.status = "persisting_raw"
            merge = self.parquet_store.merge_raw_calls(request.country.value, rows)
            job.records_received = sum(int(row.get("row_count") or 0) for row in rows)
            job.records_persisted = merge.rows_captured
            job.pages_processed = 2
            job.status = "building_derived_datasets"
            build = build_derived_datasets(
                self.parquet_store,
                request.country.value,
                raw_calls=rows,
                ingestion_id=job.ingestion_id,
            )
            job.status = "running_regression"
            report = run_regression(
                self.parquet_store,
                request.country.value,
                ingestion_id=job.ingestion_id,
            )
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
