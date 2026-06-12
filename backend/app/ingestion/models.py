from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.app.quantum.schemas import Country


class IngestionCreate(BaseModel):
    country: Country
    dashboard_url: str | None = None
    wait_seconds: int = Field(default=35, ge=5, le=180)


class IngestionJob(BaseModel):
    ingestion_id: str
    country: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    started_at: datetime
    finished_at: datetime | None = None
    endpoint_current: str | None = None
    records_received: int = 0
    records_persisted: int = 0
    pages_processed: int = 0
    errors: list[str] = Field(default_factory=list)
    duration_seconds: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)
