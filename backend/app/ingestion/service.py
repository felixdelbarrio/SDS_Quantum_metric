from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from backend.app.auth.browser_cookies import BrowserCookieProvider, CookieAccessError
from backend.app.auth.session_store import secret_store
from backend.app.config.settings import Settings
from backend.app.ingestion.models import IngestionCreate, IngestionJob
from backend.app.ingestion.planner import IngestionChunk, plan_ingestion_chunks
from backend.app.ingestion.policy import IngestionRange, build_ingestion_range
from backend.app.ingestion.progress import update_progress
from backend.app.observability.sanitizer import sanitize_error
from backend.app.quantum.config_store import QuantumConfigStore
from backend.app.quantum_dashboard.builder import build_derived_datasets
from backend.app.quantum_dashboard.capture import capture_quantum_dashboard_cards
from backend.app.quantum_dashboard.card_mapper import map_card_role
from backend.app.quantum_dashboard.discovery import discover_dashboard_from_config
from backend.app.quantum_dashboard.models import DerivedBuildResult, RegressionReport
from backend.app.quantum_dashboard.periods import parse_date, zoneinfo_for
from backend.app.quantum_dashboard.regression import REGRESSION_REPORT_PATH, run_regression
from backend.app.storage.parquet_store import ParquetStore, RawCallMergeResult


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

    def start_missing_days(self, request: IngestionCreate) -> IngestionJob:
        if not request.days:
            raise ValueError("Missing-days ingestion needs at least one day.")
        return self.start(request)

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
            explicit_range = _explicit_range_from_request(request)
            day_chunks = [] if explicit_range else _chunks_for_requested_days(request.days)
            if explicit_range:
                ingestion_range = explicit_range
            elif day_chunks:
                ingestion_range = IngestionRange(
                    mode="backfill",
                    start=min(chunk.start for chunk in day_chunks),
                    end=max(chunk.end for chunk in day_chunks),
                    latest_source_end=None,
                    lookback_days=len(day_chunks),
                    range_key=request.range_key or "custom",
                    capture_mode="daily",
                )
            else:
                preset_range = _preset_range(request.range_key)
                if preset_range:
                    ingestion_range = preset_range
                else:
                    legacy_range = build_ingestion_range(
                        self.parquet_store.latest_source_end(request.country.value),
                        depth_days=config.ingestion_depth_days,
                        incremental_reprocess_days=self.settings.quantum_incremental_reprocess_days,
                    )
                    ingestion_range = IngestionRange(
                        mode=legacy_range.mode,
                        start=legacy_range.start,
                        end=legacy_range.end,
                        latest_source_end=legacy_range.latest_source_end,
                        lookback_days=legacy_range.lookback_days,
                        range_key=request.range_key or "default",
                        capture_mode="daily",
                    )
            country_config = config.required_country_config(request.country)
            dashboard = country_config.default_dashboard()
            if not dashboard or not dashboard.dashboard_id:
                raise RuntimeError(
                    f"No hay dashboard default configurado para {request.country.value}. "
                    "Ve a Configuracion y selecciona un dashboard default para el pais."
                )
            if not dashboard.validated:
                raise RuntimeError(
                    f"El dashboard default de {request.country.value} no esta validado. "
                    "Ve a Configuracion y actualiza dashboards."
                )
            enabled_roles = set(country_config.enabled_widget_roles())
            if not enabled_roles:
                raise RuntimeError(
                    f"No hay widgets habilitados para {request.country.value}. "
                    "Ve a Configuracion y habilita al menos un widget."
                )
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
                capture_session_mode = config.session_mode.value
            elif config.session_mode == "controlled":
                try:
                    cookies = self.cookie_provider.load(
                        config.browser.value, str(discovery.base_url)
                    )
                    capture_session_mode = "browser"
                except CookieAccessError:
                    cookies = []
                    capture_session_mode = config.session_mode.value
            else:
                cookies = self.cookie_provider.load(config.browser.value, str(discovery.base_url))
                capture_session_mode = config.session_mode.value
            chunks = day_chunks or plan_ingestion_chunks(
                ingestion_range,
                chunk_days=(
                    max(1, self.settings.quantum_ingestion_chunk_days)
                    if ingestion_range.capture_mode == "daily"
                    else 3650
                ),
            )
            if ingestion_range.capture_mode == "range_contract":
                chunks_to_capture = chunks
            else:
                covered_ranges = self.parquet_store.covered_source_ranges(request.country.value)
                chunks_to_capture = [
                    chunk
                    for chunk in chunks
                    if day_chunks or not _is_chunk_covered(chunk, covered_ranges)
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
            chunk_indexes = {chunk: index for index, chunk in enumerate(chunks, start=1)}
            skipped_chunks = len(chunks) - len(chunks_to_capture)
            merge: RawCallMergeResult | None = None
            build: DerivedBuildResult | None = None
            report: RegressionReport | None = None
            rows_replaced = 0
            rows_after_merge = 0
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
                    status="capturing_day" if day_chunks else "capturing_chunk",
                    completed_chunks=skipped_chunks + capture_index - 1,
                    message=f"Capturando chunk {index}/{len(chunks)} {chunk.label}.",
                )

                chunk_label = chunk.label
                chunk_count = len(chunks)
                chunk_index = index

                def progress_callback(
                    tab_name: str,
                    *,
                    chunk_index: int = chunk_index,
                    chunk_count: int = chunk_count,
                    chunk_label: str = chunk_label,
                ) -> None:
                    tab_label = "Resumen" if tab_name == "summary" else "Errores"
                    update_progress(
                        job,
                        status=(
                            "capturing_summary_tab"
                            if tab_name == "summary"
                            else "capturing_errors_tab"
                        ),
                        current_tab=tab_label,
                        message=(
                            f"Capturando {tab_label} para chunk "
                            f"{chunk_index}/{chunk_count} {chunk_label}."
                        ),
                    )

                chunk_range = ingestion_range.__class__(
                    mode=ingestion_range.mode,
                    start=chunk.start,
                    end=chunk.end,
                    latest_source_end=ingestion_range.latest_source_end,
                    lookback_days=ingestion_range.lookback_days,
                    range_key=ingestion_range.range_key,
                    timezone=ingestion_range.timezone,
                    capture_mode=ingestion_range.capture_mode,
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
                    session_mode=capture_session_mode,
                    progress_callback=progress_callback,
                )
                captured = _filter_enabled_rows(captured, enabled_roles)
                captured = [
                    {
                        **row,
                        "dashboard_id": row.get("dashboard_id") or discovery.dashboard_id,
                        "dashboard_name": dashboard.name,
                        "dashboard_source": dashboard.source,
                        "team_id": row.get("team_id") or dashboard.team_id or discovery.team_id,
                        "widget_id": row.get("widget_id") or row.get("card_id"),
                        "widget_type": row.get("widget_type") or row.get("card_type"),
                        "visual_role": row.get("visual_role") or row.get("card_role"),
                    }
                    for row in captured
                ]
                if not captured:
                    raise RuntimeError(
                        "No Quantum analytics responses were captured for "
                        f"{request.country.value} {chunk.label}. "
                        "Check that the selected Quantum session is authenticated and "
                        "that the dashboard emits /analytics responses for this range."
                    )
                chunk_rows = sum(int(row.get("row_count") or 0) for row in captured)
                merge, build, report = _publish_completed_chunk(
                    self.parquet_store,
                    request.country.value,
                    captured,
                    job.ingestion_id,
                    enabled_roles,
                    dashboard_id=discovery.dashboard_id,
                    dashboard_name=dashboard.name,
                    range_key=ingestion_range.range_key,
                )
                rows_replaced += merge.rows_replaced if merge else 0
                rows_after_merge = merge.rows_after if merge else rows_after_merge
                job.records_received += chunk_rows
                job.records_persisted += merge.rows_captured if merge else 0
                job.calls_captured += len(captured)
                job.rows_captured = job.records_received
                job.mandatory_cards_total = (
                    build.mandatory_cards if build else job.mandatory_cards_total
                )
                job.mandatory_cards_captured = (
                    build.mandatory_cards_captured if build else job.mandatory_cards_captured
                )
                job.derived_datasets = build.derived_datasets if build else job.derived_datasets
                job.regression_status = report.status if report else job.regression_status
                update_progress(
                    job,
                    completed_chunks=skipped_chunks + capture_index,
                    calls_captured=job.calls_captured,
                    rows_captured=job.rows_captured,
                    message=(
                        f"Chunk {index}/{len(chunks)} publicado; "
                        "dashboard actualizado con los datos disponibles."
                    ),
                )
                _set_chunk_status(job, index, "completed")
            job.pages_processed = 2
            if not chunks_to_capture:
                update_progress(
                    job,
                    status="building_derived",
                    message="Actualizando dashboard con chunks ya disponibles.",
                )
                build = build_derived_datasets(
                    self.parquet_store,
                    request.country.value,
                    ingestion_id=job.ingestion_id,
                    enabled_roles=enabled_roles,
                    dashboard_id=discovery.dashboard_id,
                    dashboard_name=dashboard.name,
                    range_key=ingestion_range.range_key,
                )
                update_progress(job, status="running_regression", message="Ejecutando regresion.")
                report = run_regression(
                    self.parquet_store,
                    request.country.value,
                    ingestion_id=job.ingestion_id,
                    enabled_roles=enabled_roles,
                    dashboard_id=discovery.dashboard_id,
                    range_key=ingestion_range.range_key,
                )
            elif build and report:
                update_progress(
                    job,
                    status="running_regression",
                    message="Validacion incremental disponible para dashboard.",
                )
            else:
                update_progress(
                    job,
                    status="building_derived",
                    message="Sin nuevas filas capturadas; dashboard mantiene datos previos.",
                )
            if build is None:
                build = build_derived_datasets(
                    self.parquet_store,
                    request.country.value,
                    ingestion_id=job.ingestion_id,
                    enabled_roles=enabled_roles,
                    dashboard_id=discovery.dashboard_id,
                    dashboard_name=dashboard.name,
                    range_key=ingestion_range.range_key,
                )
            if report is None:
                report = run_regression(
                    self.parquet_store,
                    request.country.value,
                    ingestion_id=job.ingestion_id,
                    enabled_roles=enabled_roles,
                    dashboard_id=discovery.dashboard_id,
                    range_key=ingestion_range.range_key,
                )
            job.mandatory_cards_total = build.mandatory_cards
            job.mandatory_cards_captured = build.mandatory_cards_captured
            job.derived_datasets = build.derived_datasets
            job.regression_status = report.status
            job.details = {
                "parquet_path": str(merge.path) if merge and merge.path else None,
                "raw_calls": job.calls_captured,
                "rows_replaced": rows_replaced,
                "rows_after_merge": rows_after_merge,
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
                "regression_report": REGRESSION_REPORT_PATH,
                "range": ingestion_range.details(),
                "requested_days": request.days,
                "dashboard": discovery.model_dump(mode="json"),
                "enabled_roles": sorted(enabled_roles),
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
            failure = sanitize_error(exc)
            job.errors.append(failure)
            job.details.update(
                {
                    "failure": failure,
                    "failure_stage": job.status,
                    "endpoint_current": job.endpoint_current,
                    "current_chunk_index": job.current_chunk_index,
                    "current_chunk_start": job.current_chunk_start,
                    "current_chunk_end": job.current_chunk_end,
                }
            )
            if job.current_chunk_index is not None:
                _set_chunk_status(job, job.current_chunk_index, "failed")
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


def _chunks_for_requested_days(days: list[str]) -> list[IngestionChunk]:
    parsed_days = sorted(
        day for day in {_parse_requested_day(day) for day in days} if day is not None
    )
    chunks: list[IngestionChunk] = []
    for day in parsed_days:
        start, end = _day_bounds(day)
        chunks.append(IngestionChunk(start=start, end=end, label=day.isoformat()))
    return chunks


def _explicit_range_from_request(request: IngestionCreate) -> IngestionRange | None:
    zone = zoneinfo_for("CST")
    today = datetime.now(zone).date()
    start_day = parse_date(request.start_date)
    end_day = parse_date(request.end_date)
    if start_day is None and end_day is None:
        return None
    start_day = start_day or end_day
    end_day = end_day or start_day
    if start_day is None or end_day is None:
        return None
    if end_day < start_day:
        start_day, end_day = end_day, start_day
    start, _ = _day_bounds(start_day)
    _, end = _day_bounds(end_day)
    if end_day >= today:
        end = min(end, _quantum_relative_range_end())
    if end < start:
        end = start
    return IngestionRange(
        mode="backfill",
        start=start,
        end=end,
        latest_source_end=None,
        lookback_days=(end_day - start_day).days + 1,
        range_key=request.range_key or "default",
        capture_mode="range_contract",
    )


def _preset_range(range_key: str | None, *, now: datetime | None = None) -> IngestionRange | None:
    if not range_key:
        return None
    key = range_key.strip().lower()
    zone = zoneinfo_for("CST")
    today = (now.astimezone(zone) if now else datetime.now(zone)).date()
    if key == "today":
        start_day = end_day = today
        dynamic_end = True
    elif key == "yesterday":
        start_day = end_day = today - timedelta(days=1)
        dynamic_end = False
    elif key == "last_7_days":
        start_day = today - timedelta(days=6)
        end_day = today
        dynamic_end = True
    else:
        return None
    start, _ = _day_bounds(start_day)
    _, end = _day_bounds(end_day)
    if dynamic_end:
        end = min(end, _quantum_relative_range_end(now))
    if end < start:
        end = start
    return IngestionRange(
        mode="backfill",
        start=start,
        end=end,
        latest_source_end=None,
        lookback_days=(end_day - start_day).days + 1,
        range_key=key,
        capture_mode="range_contract",
    )


def _quantum_relative_range_end(now: datetime | None = None) -> datetime:
    zone = zoneinfo_for("CST")
    local_now = now.astimezone(zone) if now else datetime.now(zone)
    current_hour_start = local_now.replace(minute=0, second=0, microsecond=0)
    return (current_hour_start - timedelta(hours=1, seconds=1)).astimezone(UTC)


def _parse_requested_day(value: str) -> date | None:
    return parse_date(value)


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    zone = zoneinfo_for("CST")
    start = datetime.combine(day, datetime.min.time(), tzinfo=zone).astimezone(UTC)
    end = datetime.combine(day, datetime.max.time().replace(microsecond=0), tzinfo=zone).astimezone(
        UTC
    )
    return start, end


def _publish_completed_chunk(
    store: ParquetStore,
    country: str,
    rows: list[dict[str, Any]],
    ingestion_id: str,
    enabled_roles: set[str],
    dashboard_id: str | None = None,
    dashboard_name: str | None = None,
    range_key: str | None = None,
) -> tuple[RawCallMergeResult | None, DerivedBuildResult, RegressionReport]:
    resolved_range_key = range_key or _range_key_from_rows(rows)
    merge = store.merge_raw_calls(country, rows) if rows else None
    build = build_derived_datasets(
        store,
        country,
        ingestion_id=ingestion_id,
        enabled_roles=enabled_roles,
        dashboard_id=dashboard_id,
        dashboard_name=dashboard_name,
        range_key=resolved_range_key,
    )
    report = run_regression(
        store,
        country,
        ingestion_id=ingestion_id,
        enabled_roles=enabled_roles,
        dashboard_id=dashboard_id,
        range_key=resolved_range_key,
    )
    return merge, build, report


def _range_key_from_rows(rows: list[dict[str, Any]]) -> str:
    for row in rows:
        value = str(row.get("range_key") or "").strip()
        if value:
            return value
    return "today"


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


def _filter_enabled_rows(
    rows: list[dict[str, Any]],
    enabled_roles: set[str],
) -> list[dict[str, Any]]:
    card_roles_by_id: dict[str, set[str]] = {}
    for row in rows:
        role = map_card_role(row)
        card_id = str(row.get("card_id") or "")
        if role is not None and card_id:
            card_roles_by_id.setdefault(card_id, set()).add(str(role))
    filtered: list[dict[str, Any]] = []
    for row in rows:
        role = map_card_role(row)
        card_id = str(row.get("card_id") or "")
        resolved_role = str(role) if role is not None else None
        inferred_roles = card_roles_by_id.get(card_id, set())
        if resolved_role is None and len(inferred_roles) == 1:
            resolved_role = next(iter(inferred_roles))
        if resolved_role is not None:
            if resolved_role in enabled_roles:
                filtered.append({**row, "card_role": resolved_role})
            continue
        filtered.append(row)
    return filtered
