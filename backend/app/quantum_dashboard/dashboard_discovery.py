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
QUANTUM_GRAPHQL_ENDPOINT = "https://api.quantummetric.com/query"
RESOURCES_LIST_QUERY = """
        query resourcesList(
            $userId: ID!
            $resourceFilter: ResourceFilter
            $pagination: PaginationInfo
        ) {
            resources(userId: $userId, filter: $resourceFilter, pagination: $pagination) {
                totalCount
                resources {
                    id
                    type
                    name
                    lastEditedAt
                    highestAccessLevel
                    starred
                    tags {
                        id
                        name
                    }
                    entity {
                        ... on Filter {
                        id
                        json
                        description
                        version
                        }
                    }
                }
            }
            resourceTags {
                id
                name
            }
        }
    """


class QuantumDashboardSummary(BaseModel):
    dashboard_id: str
    name: str
    type: str = "dashboard"
    team_id: str | None = None
    country: Country
    order: int | None = None
    is_default_candidate: bool = False
    source: DashboardSource
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


async def discover_dashboards_for_country(
    country: Country,
    base_url: str,
    session: Any,
    *,
    force_refresh: bool = False,
) -> list[QuantumDashboardSummary]:
    _ = force_refresh
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
            order=index,
            is_default_candidate=dashboard.is_default,
            source="config_cache",
            discovered_at=dashboard.discovered_at or timestamp,
        )
        for index, dashboard in enumerate(country_config.dashboards)
        if dashboard.dashboard_id
    ]
    return dedupe_dashboard_summaries(rows)


def dedupe_dashboard_summaries(
    summaries: Sequence[QuantumDashboardSummary],
) -> list[QuantumDashboardSummary]:
    by_id: dict[str, QuantumDashboardSummary] = {}
    order_by_id: dict[str, int] = {}
    for summary in summaries:
        if not summary.dashboard_id:
            continue
        existing = by_id.get(summary.dashboard_id)
        if existing is None:
            by_id[summary.dashboard_id] = summary
            order_by_id[summary.dashboard_id] = len(order_by_id)
            continue
        if existing.source == "config_cache" and summary.source != "config_cache":
            by_id[summary.dashboard_id] = _merge_summary(existing, summary)
            continue
        if existing.order is not None and summary.order is None:
            by_id[summary.dashboard_id] = existing.model_copy(
                update={
                    "team_id": existing.team_id or summary.team_id,
                    "type": existing.type or summary.type,
                    "is_default_candidate": existing.is_default_candidate
                    or summary.is_default_candidate,
                }
            )
            continue
        if len(summary.name) > len(existing.name) and summary.name != summary.dashboard_id:
            by_id[summary.dashboard_id] = _merge_summary(existing, summary)
    return sorted(
        by_id.values(),
        key=lambda item: (
            item.order if item.order is not None else order_by_id.get(item.dashboard_id, 0),
            item.name.casefold(),
        ),
    )


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
    query_context: dict[str, Any] | None = None
    query_context_ref: dict[str, dict[str, Any] | None] = {"value": None}
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
            page.on("request", lambda request: _capture_query_context(request, query_context_ref))
            page.on(
                "response",
                lambda response: _collect_resources_list_payload(response, payloads),
            )
            page.goto(_dashboard_home_url(base_url), wait_until="domcontentloaded", timeout=60_000)
            query_context = _wait_for_query_context(
                page,
                query_context_ref,
                wait_seconds,
            )
            if query_context is not None:
                payload = _resources_list_payload(str(query_context["user_id"]))
                response = context.request.post(
                    QUANTUM_GRAPHQL_ENDPOINT,
                    headers=cast(dict[str, str], query_context["headers"]),
                    data=payload,
                    timeout=60_000,
                )
                if response.ok:
                    payloads.append(response.json())
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
            elif not payloads and query_context is None:
                error = "Quantum Web did not expose an authenticated resourcesList request."
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

    rows = _resource_list_summaries(
        value,
        country=country,
        source=source,
        discovered_at=discovered_at,
    )
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
    order = _int_or_none(item.get("order") or item.get("position") or item.get("index"))
    return QuantumDashboardSummary(
        dashboard_id=dashboard_id,
        name=name,
        type=candidate_type,
        team_id=team_id,
        country=country,
        order=order,
        is_default_candidate=bool(item.get("starred") or item.get("isDefault")),
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
            "order": incoming.order if incoming.order is not None else existing.order,
            "is_default_candidate": incoming.is_default_candidate or existing.is_default_candidate,
        }
    )


def _resource_list_summaries(
    payload: dict[str, Any],
    *,
    country: Country,
    source: DashboardSource,
    discovered_at: datetime,
) -> list[QuantumDashboardSummary]:
    resources = payload.get("resources")
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("resources"), dict):
        resources = data.get("resources")
    if not isinstance(resources, dict) or not isinstance(resources.get("resources"), list):
        return []

    rows: list[QuantumDashboardSummary] = []
    for index, item in enumerate(resources["resources"]):
        if not isinstance(item, dict):
            continue
        if (_text(item.get("type")) or "").casefold() != "dashboard":
            continue
        dashboard_id = _text(item.get("id") or item.get("dashboardId"))
        name = _text(item.get("name") or item.get("title") or dashboard_id)
        if not dashboard_id or not name:
            continue
        team_id = _text(item.get("teamID") or item.get("teamId") or item.get("team_id"))
        rows.append(
            QuantumDashboardSummary(
                dashboard_id=dashboard_id,
                name=name,
                type=_text(item.get("type")) or "DASHBOARD",
                team_id=team_id,
                country=country,
                order=index,
                is_default_candidate=bool(item.get("starred") or item.get("isDefault")),
                source=source,
                discovered_at=discovered_at,
            )
        )
    return rows


def _resources_list_payload(user_id: str, *, first: int = 0, size: int = 100) -> dict[str, Any]:
    return {
        "operationName": "resourcesList",
        "query": RESOURCES_LIST_QUERY,
        "variables": {
            "userId": user_id,
            "resourceFilter": {"namePrefix": "", "types": ["DASHBOARD"], "tags": []},
            "pagination": {
                "first": first,
                "size": size,
                "orderBy": "LAST_EDITED_AT",
                "order": "Desc",
            },
        },
    }


def _capture_query_context(
    request: Any,
    query_context_ref: dict[str, dict[str, Any] | None],
) -> None:
    if query_context_ref.get("value") is not None:
        return
    context = _query_context_from_request(request)
    if context is not None:
        query_context_ref["value"] = context


def _query_context_from_request(request: Any) -> dict[str, Any] | None:
    try:
        if str(request.method).upper() != "POST" or not _is_quantum_graphql_url(request.url):
            return None
        headers = {str(key).lower(): str(value) for key, value in request.headers.items()}
        if not headers.get("authorization"):
            return None
        body = _parse_request_json(request)
        variables = body.get("variables") if isinstance(body, dict) else None
        user_id = _text(variables.get("userId") if isinstance(variables, dict) else None)
        if not user_id:
            return None
        safe_headers = {
            key: value
            for key, value in headers.items()
            if key in {"authorization", "content-type", "referer", "user-agent"}
            or key.startswith("x-")
        }
        safe_headers.setdefault("content-type", "application/json")
        return {"headers": safe_headers, "user_id": user_id}
    except Exception:
        return None


def _wait_for_query_context(
    page: Any,
    query_context_ref: dict[str, dict[str, Any] | None],
    wait_seconds: int,
) -> dict[str, Any] | None:
    started = time.monotonic()
    deadline = started + max(5, min(wait_seconds, 45))
    while time.monotonic() < deadline:
        if query_context_ref.get("value") is not None:
            return query_context_ref["value"]
        page.wait_for_timeout(500)
    return query_context_ref.get("value")


def _collect_resources_list_payload(response: Any, payloads: list[Any]) -> None:
    try:
        content_type = str(response.headers.get("content-type") or "")
        if "json" not in content_type.casefold():
            return
        if not _is_quantum_graphql_url(response.url):
            return
        request_body = _parse_request_json(response.request)
        operation_name = (
            _text(request_body.get("operationName")) if isinstance(request_body, dict) else None
        )
        query_text = _text(request_body.get("query")) if isinstance(request_body, dict) else None
        if operation_name != "resourcesList" and "resources" not in (query_text or ""):
            return
        body = response.body()
        if len(body) > 4_000_000:
            return
        payload = json.loads(body.decode("utf-8", "replace"))
    except Exception:
        return
    if _resource_list_summaries(
        payload,
        country=Country.MX,
        source="quantum_web",
        discovered_at=datetime.now(UTC),
    ):
        payloads.append(payload)


def _parse_request_json(request: Any) -> dict[str, Any]:
    try:
        payload = request.post_data_json
        if callable(payload):
            payload = payload()
        return payload if isinstance(payload, dict) else {}
    except Exception:
        raw = getattr(request, "post_data", None) or ""
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}


def _is_quantum_graphql_url(url: str) -> bool:
    parsed = urlparse(str(url))
    hostname = (parsed.hostname or "").casefold()
    allowed_host = hostname == "quantummetric.com" or hostname.endswith(".quantummetric.com")
    return allowed_host and parsed.path.rstrip("/") == "/query"


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


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
