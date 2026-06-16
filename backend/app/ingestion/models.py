from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.app.quantum.schemas import Country


class IngestionCreate(BaseModel):
    country: Country


class IngestionJob(BaseModel):
    ingestion_id: str
    country: str
    status: Literal[
        "pending",
        "running",
        "capturing_web",
        "capturing_summary_tab",
        "capturing_errors_tab",
        "persisting_raw",
        "building_contracts",
        "building_derived_datasets",
        "running_regression",
        "completed",
        "completed_with_warnings",
        "failed",
        "failed_regression",
        "cancelled",
    ]
    started_at: datetime
    finished_at: datetime | None = None
    endpoint_current: str | None = None
    records_received: int = 0
    records_persisted: int = 0
    pages_processed: int = 0
    errors: list[str] = Field(default_factory=list)
    duration_seconds: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)
