from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.app.quantum.schemas import Country


class IngestionCreate(BaseModel):
    country: Country
    days: list[str] = Field(default_factory=list)
    range_key: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class MissingDaysIngestionCreate(BaseModel):
    country: Country
    days: list[str] = Field(min_length=1)
    range_key: str = "custom"
    start_date: str | None = None
    end_date: str | None = None


class RangeIngestionCreate(BaseModel):
    country: Country
    range_key: str = "custom"
    start_date: str
    end_date: str
    reason: str = "user_requested"


class IngestionJob(BaseModel):
    ingestion_id: str
    country: str
    status: Literal[
        "pending",
        "running",
        "planning_range",
        "planning_chunks",
        "capturing_chunk",
        "capturing_day",
        "capturing_required_cards",
        "capturing_web",
        "capturing_summary_tab",
        "capturing_errors_tab",
        "persisting_raw",
        "building_derived",
        "building_contracts",
        "building_derived_datasets",
        "running_regression",
        "completed",
        "completed_with_warnings",
        "failed",
        "failed_no_session",
        "failed_dashboard_not_found",
        "failed_no_widgets",
        "failed_no_analytics_responses",
        "failed_regression",
        "cancelled",
        "cancelled_by_user",
    ]
    started_at: datetime
    finished_at: datetime | None = None
    endpoint_current: str | None = None
    records_received: int = 0
    records_persisted: int = 0
    pages_processed: int = 0
    planned_chunks: int = 0
    completed_chunks: int = 0
    current_chunk_index: int | None = None
    current_chunk_start: str | None = None
    current_chunk_end: str | None = None
    chunks: list[dict[str, Any]] = Field(default_factory=list)
    mandatory_cards_total: int = 9
    mandatory_cards_captured: int = 0
    current_card_role: str | None = None
    current_tab: str | None = None
    calls_captured: int = 0
    rows_captured: int = 0
    derived_datasets: int = 0
    regression_status: str | None = None
    progress_percent: float = 0.0
    last_progress_at: datetime | None = None
    message: str | None = None
    errors: list[str] = Field(default_factory=list)
    duration_seconds: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)
