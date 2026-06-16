from __future__ import annotations

from typing import Literal
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from backend.app.config.settings import Settings
from backend.app.quantum.schemas import QuantumCountryConfig
from backend.app.quantum_dashboard.models import DashboardDiscoveryResult


def discover_dashboard_from_config(
    *,
    settings: Settings,
    country_config: QuantumCountryConfig,
    url: str | None = None,
) -> DashboardDiscoveryResult:
    base_url = country_config.base_url or settings.quantum_default_base_url
    configured_dashboard_id = country_config.dashboard_id or settings.quantum_default_dashboard_id
    configured_team_id = country_config.team_id or settings.quantum_default_team_id
    configured_summary_tab = country_config.tab or settings.quantum_default_summary_tab
    parsed = parse_dashboard_url(url or "")

    dashboard_id = configured_dashboard_id or parsed.dashboard_id
    team_id = configured_team_id or parsed.team_id
    summary_tab = parsed.tab if parsed.tab is not None else configured_summary_tab
    errors_tab = settings.quantum_default_errors_tab

    if dashboard_id:
        source: Literal["env", "url", "metadata", "default", "unresolved"] = (
            "env" if configured_dashboard_id else "url"
        )
        message = (
            "Dashboard resolved from configuration."
            if source == "env"
            else "Dashboard resolved from URL."
        )
    else:
        source = "unresolved"
        message = "Dashboard could not be resolved from .env, local config, or URL."

    return DashboardDiscoveryResult(
        country=country_config.country.value,
        base_url=base_url,
        dashboard_id=dashboard_id or None,
        team_id=team_id or None,
        summary_tab=summary_tab,
        errors_tab=errors_tab,
        tabs=[
            {"name": "Resumen", "tab": summary_tab, "role": "summary"},
            {"name": "Errores", "tab": errors_tab, "role": "errors"},
        ],
        source=source,
        message=message,
    )


def dashboard_tab_url(
    *,
    base_url: str,
    dashboard_id: str,
    team_id: str | None,
    tab: int,
) -> str:
    parsed = urlparse(base_url)
    origin = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
    query = urlencode({"tab": tab, **({"teamID": team_id} if team_id else {})})
    return f"{origin.rstrip()}/#/dashboard/{dashboard_id}?{query}"


class ParsedDashboardUrl:
    def __init__(self, dashboard_id: str, team_id: str, tab: int | None) -> None:
        self.dashboard_id = dashboard_id
        self.team_id = team_id
        self.tab = tab


def parse_dashboard_url(url: str) -> ParsedDashboardUrl:
    if not url:
        return ParsedDashboardUrl("", "", None)
    parsed = urlparse(url)
    fragment = urlparse(parsed.fragment) if parsed.fragment else parsed
    parts = [part for part in fragment.path.split("/") if part]
    dashboard_id = parts[1] if len(parts) >= 2 and parts[0] == "dashboard" else ""
    params = parse_qs(fragment.query)
    team_id = _first_text(params.get("teamID"), "")
    tab = _first_int(params.get("tab"))
    return ParsedDashboardUrl(dashboard_id, team_id, tab)


def _first_text(values: list[str] | None, default: str) -> str:
    if not values:
        return default
    return values[0]


def _first_int(values: list[str] | None) -> int | None:
    if not values:
        return None
    try:
        return int(values[0])
    except ValueError:
        return None
