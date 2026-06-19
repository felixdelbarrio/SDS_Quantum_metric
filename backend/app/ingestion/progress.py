from __future__ import annotations

from datetime import UTC, datetime

from backend.app.ingestion.models import IngestionJob


def update_progress(
    job: IngestionJob,
    *,
    status: str | None = None,
    message: str | None = None,
    completed_chunks: int | None = None,
    calls_captured: int | None = None,
    rows_captured: int | None = None,
    mandatory_cards_captured: int | None = None,
    current_card_role: str | None = None,
    current_tab: str | None = None,
) -> None:
    if status is not None:
        job.status = status  # type: ignore[assignment]
    if message is not None:
        job.message = message
    if completed_chunks is not None:
        job.completed_chunks = completed_chunks
    if calls_captured is not None:
        job.calls_captured = calls_captured
        job.records_persisted = calls_captured
    if rows_captured is not None:
        job.rows_captured = rows_captured
        job.records_received = rows_captured
    if mandatory_cards_captured is not None:
        job.mandatory_cards_captured = mandatory_cards_captured
    if current_card_role is not None:
        job.current_card_role = current_card_role
    if current_tab is not None:
        job.current_tab = current_tab
    job.progress_percent = _progress_percent(job)
    job.last_progress_at = datetime.now(UTC)


def _progress_percent(job: IngestionJob) -> float:
    chunk_weight = 70.0
    card_weight = 20.0
    tail_weight = (
        10.0 if job.status in {"building_derived", "running_regression", "completed"} else 0.0
    )
    capture_floor = {
        "capturing_chunk": 5.0,
        "capturing_day": 5.0,
        "capturing_summary_tab": 15.0,
        "capturing_errors_tab": 35.0,
    }.get(job.status, 0.0)
    chunk_part = (
        (job.completed_chunks / job.planned_chunks) * chunk_weight if job.planned_chunks else 0.0
    )
    card_part = (
        (job.mandatory_cards_captured / job.mandatory_cards_total) * card_weight
        if job.mandatory_cards_total
        else 0.0
    )
    return round(min(100.0, max(capture_floor, chunk_part + card_part + tail_weight)), 2)
