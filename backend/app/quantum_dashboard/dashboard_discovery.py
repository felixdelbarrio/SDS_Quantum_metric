from __future__ import annotations

import inspect
import json
import time
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any, Literal, cast
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, Field

from backend.app.auth.browser_cookies import BrowserCookie
from backend.app.config.settings import Settings
from backend.app.ingestion.capture import (
    _configure_playwright_browser_path,
    _launch_headless_browser,
    _looks_unauthenticated,
)
from backend.app.observability.sanitizer import sanitize_error
from backend.app.quantum.schemas import Country, QuantumCountryConfig

DashboardSource = Literal["quantum_api", "quantum_web", "config_cache"]


class QuantumDashboardSummary(BaseModel):
    dashboard_id: str
    name: str
    type: str = "dashboard"
    team_id: str | None = None
    country: Country
    source: DashboardSource
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


async def discover_dashboards_for_country(
    country: Country,
    base_url: str,
    session: Any,
) -> list[QuantumDashboardSummary]:
    payloads = await _payloads_from_session(session)
    summaries = discover_dashboards_from_payloads(
        payloads,
        country=country,
        source="quantum_api",
    )
    if summaries:
        return summaries

    cache = getattr(session, "config_cache", None)
    if isinstance(cache, QuantumCountryConfig):
        return dashboards_from_config_cache(cache)
    if isinstance(cache, Iterable):
        cached_summaries: list[QuantumDashboardSummary] = []
        for item in cache:
            if isinstance(item, QuantumCountryConfig):
                cached_summaries.extend(dashboards_from_config_cache(item))
        if cached_summaries:
            return dedupe_dashboard_summaries(cached_summaries)
    _ = base_url
    return []


def discover_dashboards_from_payloads(
    payloads: Sequence[Any],
    *,
    country: Country,
    source: DashboardSource,
    discovered_at: datetime | None = None,
) -> list[QuantumDashboardSummary]:
    rows: list[QuantumDashboardSummary] = []
    timestamp = discovered_at or datetime.now(UTC)
    for payload in payloads:
        rows.extend(
            _extract_dashboard_summaries(
                payload,
                country=country,
                source=source,
                discovered_at=timestamp,
                path=(),
            )
        )
    return dedupe_dashboard_summaries(rows)


def dashboards_from_config_cache(
    country_config: QuantumCountryConfig,
) -> list[QuantumDashboardSummary]:
    timestamp = datetime.now(UTC)
    rows = [
        QuantumDashboardSummary(
            dashboard_id=dashboard.dashboard_id,
            name=dashboard.name or dashboard.dashboard_id,
            type=dashboard.dashboard_type or "dashboard",
            team_id=dashboard.team_id or None,
            country=country_config.country,
            source="config_cache",
            discovered_at=dashboard.discovered_at or timestamp,
        )
        for dashboard in country_config.dashboards
        if dashboard.dashboard_id
    ]
    return dedupe_dashboard_summaries(rows)


def dedupe_dashboard_summaries(
    summaries: Sequence[QuantumDashboardSummary],
) -> list[QuantumDashboardSummary]:
    by_id: dict[str, QuantumDashboardSummary] = {}
    for summary in summaries:
        if not summary.dashboard_id:
            continue
        existing = by_id.get(summary.dashboard_id)
        if existing is None:
            by_id[summary.dashboard_id] = summary
            continue
        if existing.source == "config_cache" and summary.source != "config_cache":
            by_id[summary.dashboard_id] = _merge_summary(existing, summary)
            continue
        if len(summary.name) > len(existing.name) and summary.name != summary.dashboard_id:
            by_id[summary.dashboard_id] = _merge_summary(existing, summary)
    return sorted(by_id.values(), key=lambda item: item.name.casefold())


def discover_dashboards_via_browser(
    *,
    settings: Settings,
    cookies: list[BrowserCookie],
    country: Country,
    base_url: str,
    wait_seconds: int,
    session_mode: str,
) -> tuple[list[QuantumDashboardSummary], str | None]:
    _configure_playwright_browser_path()
    from playwright.sync_api import sync_playwright

    payloads: list[Any] = []
    error: str | None = None
    with sync_playwright() as playwright:
        context: Any | None = None
        browser: Any | None = None
        try:
            if session_mode == "controlled":
                user_data_dir = settings.runtime_dir / "quantum-controlled-profile"
                user_data_dir.mkdir(parents=True, exist_ok=True)
                context = playwright.chromium.launch_persistent_context(
                    str(user_data_dir),
                    headless=True,
                    ignore_https_errors=not settings.qm_verify_tls,
                    args=["--disable-dev-shm-usage", "--no-first-run"],
                )
                if cookies:
                    context.add_cookies(cast(Any, [cookie.as_playwright() for cookie in cookies]))
            else:
                browser = _launch_headless_browser(playwright, settings)
                context = browser.new_context(ignore_https_errors=not settings.qm_verify_tls)
                if cookies:
                    context.add_cookies(cast(Any, [cookie.as_playwright() for cookie in cookies]))

            page = context.new_page()
            page.on("response", lambda response: _collect_dashboard_payload(response, payloads))
            page.goto(_dashboard_home_url(base_url), wait_until="domcontentloaded", timeout=60_000)
            _wait_for_dashboard_payloads(page, payloads, wait_seconds)
            embedded = page.evaluate(
                """
                () => Array.from(document.scripts)
                  .map((node) => node.textContent || "")
                  .filter((text) => text.includes("dashboard"))
                  .slice(0, 20)
                """
            )
            if isinstance(embedded, list):
                payloads.extend(_json_objects_from_scripts(embedded))
            if not payloads and _looks_unauthenticated(page):
                error = "Quantum Web redirected to an authentication page."
            page.close()
        except Exception as exc:
            error = sanitize_error(exc)
        finally:
            if context is not None:
                context.close()
            if browser is not None:
                browser.close()

    summaries = discover_dashboards_from_payloads(
        payloads,
        country=country,
        source="quantum_web",
    )
    return summaries, error


async def _payloads_from_session(session: Any) -> list[Any]:
    for attribute in (
        "dashboard_payloads",
        "payloads",
        "get_dashboard_payloads",
        "get_payloads",
    ):
        value = getattr(session, attribute, None)
        if value is None:
            continue
        result = value() if callable(value) else value
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, list):
            return result
        if isinstance(result, tuple):
            return list(result)
    return []


def _extract_dashboard_summaries(
    value: Any,
    *,
    country: Country,
    source: DashboardSource,
    discovered_at: datetime,
    path: tuple[str, ...],
) -> list[QuantumDashboardSummary]:
    if isinstance(value, list):
        rows: list[QuantumDashboardSummary] = []
        for item in value:
            rows.extend(
                _extract_dashboard_summaries(
                    item,
                    country=country,
                    source=source,
                    discovered_at=discovered_at,
                    path=path,
                )
            )
        return rows
    if not isinstance(value, dict):
        return []

    rows = []
    summary = _summary_from_candidate(
        value,
        country=country,
        source=source,
        discovered_at=discovered_at,
        path=path,
    )
    if summary is not None:
        rows.append(summary)

    for key, child in value.items():
        rows.extend(
            _extract_dashboard_summaries(
                child,
                country=country,
                source=source,
                discovered_at=discovered_at,
                path=(*path, str(key)),
            )
        )
    return rows


def _summary_from_candidate(
    item: dict[str, Any],
    *,
    country: Country,
    source: DashboardSource,
    discovered_at: datetime,
    path: tuple[str, ...],
) -> QuantumDashboardSummary | None:
    if _text(item.get("cardId") or item.get("card_id") or item.get("widgetId")):
        return None
    dashboard_id = _text(
        item.get("dashboardId")
        or item.get("dashboardID")
        or item.get("dashboard_id")
        or item.get("dashboardUuid")
        or item.get("uuid")
        or item.get("id")
    )
    name = _text(
        item.get("dashboardName")
        or item.get("displayName")
        or item.get("name")
        or item.get("title")
    )
    if not dashboard_id or not name:
        return None
    candidate_type = (
        _text(
            item.get("dashboardType")
            or item.get("dashboard_type")
            or item.get("type")
            or item.get("kind")
        )
        or "dashboard"
    )
    path_text = ".".join(path).casefold()
    type_text = candidate_type.casefold()
    if "dashboard" not in path_text and "dashboard" not in type_text:
        if not any(key in item for key in ("tabs", "cards", "widgets", "teamID", "teamId")):
            return None
    team_id = _text(item.get("teamID") or item.get("teamId") or item.get("team_id"))
    team = item.get("team")
    if team_id is None and isinstance(team, dict):
        team_id = _text(team.get("id") or team.get("teamId") or team.get("teamID"))
    return QuantumDashboardSummary(
        dashboard_id=dashboard_id,
        name=name,
        type=candidate_type,
        team_id=team_id,
        country=country,
        source=source,
        discovered_at=discovered_at,
    )


def _merge_summary(
    existing: QuantumDashboardSummary,
    incoming: QuantumDashboardSummary,
) -> QuantumDashboardSummary:
    return incoming.model_copy(
        update={
            "team_id": incoming.team_id or existing.team_id,
            "type": incoming.type or existing.type,
        }
    )


def _collect_dashboard_payload(response: Any, payloads: list[Any]) -> None:
    try:
        content_type = str(response.headers.get("content-type") or "")
        if "json" not in content_type.casefold():
            return
        parsed = urlparse(str(response.url))
        haystack = f"{parsed.path} {parsed.query}".casefold()
        if "dashboard" not in haystack and "menu" not in haystack:
            return
        body = response.body()
        if len(body) > 4_000_000:
            return
        payload = json.loads(body.decode("utf-8", "replace"))
    except Exception:
        return
    payloads.append(payload)


def _json_objects_from_scripts(scripts: list[Any]) -> list[Any]:
    payloads: list[Any] = []
    for script in scripts:
        if not isinstance(script, str) or "dashboard" not in script.casefold():
            continue
        start = script.find("{")
        end = script.rfind("}")
        if start < 0 or end <= start:
            continue
        try:
            payloads.append(json.loads(script[start : end + 1]))
        except json.JSONDecodeError:
            continue
    return payloads


def _dashboard_home_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    origin = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
    return f"{origin.rstrip()}/#/"


def _wait_for_dashboard_payloads(page: Any, payloads: list[Any], wait_seconds: int) -> None:
    started = time.monotonic()
    deadline = started + max(5, min(wait_seconds, 45))
    while time.monotonic() < deadline:
        page.wait_for_timeout(500)
        if payloads and time.monotonic() - started >= 3:
            return


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
