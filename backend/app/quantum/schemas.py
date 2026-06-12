from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class BrowserName(StrEnum):
    chrome = "chrome"
    edge = "edge"
    safari = "safari"
    firefox = "firefox"


class SessionMode(StrEnum):
    browser = "browser"
    manual = "manual"


class Country(StrEnum):
    ES = "ES"
    MX = "MX"
    PE = "PE"
    CO = "CO"
    AR = "AR"


class QuantumConfig(BaseModel):
    browser: BrowserName = BrowserName.chrome
    base_url: str = Field(default="https://bbvamx.quantummetric.com")
    session_mode: SessionMode = SessionMode.browser
    country: Country = Country.MX
    dashboard_url: str = ""
    verify_tls: bool = True


class QuantumConfigUpdate(QuantumConfig):
    manual_cookie: str | None = Field(default=None, exclude=True)


class ConnectionState(BaseModel):
    status: Literal["not_tested", "ok", "ko"] = "not_tested"
    endpoint_tested: str | None = None
    latency_ms: float | None = None
    timestamp: datetime | None = None
    message: str = "No probado"
    error: str | None = None


class TestConnectionResponse(ConnectionState):
    details: dict[str, Any] = Field(default_factory=dict)
