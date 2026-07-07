from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse, urlunparse

from pydantic import BaseModel, Field, model_validator

from backend.app.quantum.schemas import Country
from backend.app.quantum_dashboard.dashboard_structure import (
    QuantumDashboardStructure,
    discover_dashboard_structure,
)


class ManualDashboardInput(BaseModel):
    dashboard_id: str
    team_id: str | None = None
    base_url: str | None = None
    name: str = ""
    range_key: str | None = None

    @model_validator(mode="after")
    def _require_dashboard_id(self) -> ManualDashboardInput:
        if not self.dashboard_id:
            raise ValueError("dashboard_id is required.")
        return self


class ManualDashboardRequest(BaseModel):
    url: str = ""
    dashboard_id: str = ""
    team_id: str | None = None
    base_url: str | None = None
    name: str = Field(default="")


def parse_dashboard_url_or_id(value: str) -> ManualDashboardInput:
    raw_value = value.strip()
    if raw_value and "/" not in raw_value and "?" not in raw_value and "#" not in raw_value:
        return ManualDashboardInput(dashboard_id=raw_value)
    return parse_dashboard_url(raw_value)


def parse_dashboard_url(url: str) -> ManualDashboardInput:
    parsed = urlparse(url.strip())
    fragment = urlparse(parsed.fragment) if parsed.fragment else parsed
    parts = [part for part in fragment.path.split("/") if part]
    dashboard_id = parts[1] if len(parts) >= 2 and parts[0] == "dashboard" else ""
    params = parse_qs(fragment.query)
    origin = (
        urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
        if parsed.scheme and parsed.netloc
        else None
    )
    return ManualDashboardInput(
        dashboard_id=dashboard_id,
        team_id=_first(params.get("teamID")),
        base_url=origin,
        range_key=_first(params.get("ts")),
    )


def manual_dashboard_input_from_request(
    request: ManualDashboardRequest,
    *,
    fallback_base_url: str,
) -> ManualDashboardInput:
    parsed = parse_dashboard_url_or_id(request.url) if request.url.strip() else None
    raw_url_or_id = request.url.strip()
    pasted_dashboard_id = (
        raw_url_or_id
        if raw_url_or_id and "/" not in raw_url_or_id and "?" not in raw_url_or_id
        else ""
    )
    return ManualDashboardInput(
        dashboard_id=(
            request.dashboard_id or (parsed.dashboard_id if parsed else "") or pasted_dashboard_id
        ).strip(),
        team_id=request.team_id or (parsed.team_id if parsed else None),
        base_url=request.base_url or (parsed.base_url if parsed else None) or fallback_base_url,
        name=request.name.strip(),
        range_key=parsed.range_key if parsed else None,
    )


async def validate_manual_dashboard(
    country: Country,
    dashboard_id: str,
    team_id: str | None,
    session: Any,
) -> QuantumDashboardStructure:
    return await discover_dashboard_structure(country, dashboard_id, team_id, session)


def _first(values: list[str] | None) -> str | None:
    if not values:
        return None
    value = values[0].strip()
    return value or None
