from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Literal, Protocol, cast

from pydantic import BaseModel, Field

from backend.app.config.settings import get_settings
from backend.app.quantum.schemas import Country

QUANTUM_GRAPHQL_ENDPOINT = "https://api.quantummetric.com/query"
RESOURCES_LIST_QUERY = """
query resourcesList($userId: ID!, $resourceFilter: ResourceFilter, $pagination: PaginationInfo) {
  resources(userId: $userId, filter: $resourceFilter, pagination: $pagination) {
    totalCount
    resources {
      id
      type
      name
      starred
    }
  }
}
"""

DashboardResourceSource = Literal["quantum_graphql", "manual", "cache"]


class QuantumDashboardResource(BaseModel):
    dashboard_id: str
    name: str
    type: Literal["DASHBOARD"] = "DASHBOARD"
    starred: bool = False
    country: Country
    team_id: str | None = None
    source: DashboardResourceSource
    order: int
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    stale: bool = False


class DashboardResourcesResult(BaseModel):
    country: Country
    total_count: int
    resources: list[QuantumDashboardResource]
    from_cache: bool = False
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    warning: str | None = None


class DashboardResourcesError(RuntimeError):
    pass


class _SyncRequestContext(Protocol):
    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        data: dict[str, Any],
        timeout: int,
    ) -> Any: ...


def resources_list_payload(user_id: str, *, first: int = 0, size: int = 25) -> dict[str, Any]:
    return {
        "operationName": "resourcesList",
        "query": RESOURCES_LIST_QUERY,
        "variables": {
            "userId": user_id,
            "resourceFilter": {
                "namePrefix": "",
                "types": ["DASHBOARD"],
                "isStarredByUser": False,
            },
            "pagination": {
                "first": first,
                "size": size,
                "orderBy": "LAST_EDITED_AT",
                "order": "Desc",
            },
        },
    }


async def fetch_dashboard_resources(
    country: Country,
    base_url: str,
    session: Any,
    *,
    force_refresh: bool = False,
    page_size: int = 25,
) -> DashboardResourcesResult:
    cache_dir = _session_cache_dir(session)
    if not force_refresh:
        cached = read_dashboard_resources_cache(country, cache_dir=cache_dir)
        if cached is not None:
            return cached

    try:
        user_id = await _resolve_user_id(session)
        pages = await _fetch_pages_with_session(
            session,
            user_id=user_id,
            page_size=page_size,
        )
        result = result_from_resources_payloads(
            pages,
            country=country,
            source="quantum_graphql",
        )
        if not result.resources:
            raise DashboardResourcesError(
                "Quantum resourcesList did not return DASHBOARD resources."
            )
        cached = read_dashboard_resources_cache(country, cache_dir=cache_dir)
        merged = merge_dashboard_resource_cache(cached, result)
        write_dashboard_resources_cache(merged, cache_dir=cache_dir)
        return merged
    except Exception as exc:
        cached = read_dashboard_resources_cache(country, cache_dir=cache_dir)
        if cached is not None:
            return cached.model_copy(
                update={
                    "from_cache": True,
                    "warning": f"No se pudo actualizar Quantum; se usa cache local: {exc}",
                }
            )
        _ = base_url
        raise DashboardResourcesError(
            "No se pudo listar dashboards en Quantum y no existe cache local."
        ) from exc


def fetch_resource_payloads_via_sync_request(
    request_context: _SyncRequestContext,
    *,
    headers: dict[str, str],
    user_id: str,
    page_size: int = 25,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    first = 0
    total_count: int | None = None
    bounded_size = max(1, min(page_size, 100))
    while total_count is None or first < total_count:
        payload = resources_list_payload(user_id, first=first, size=bounded_size)
        response = request_context.post(
            QUANTUM_GRAPHQL_ENDPOINT,
            headers=headers,
            data=payload,
            timeout=60_000,
        )
        if not getattr(response, "ok", False):
            break
        body = response.json()
        if not isinstance(body, dict):
            break
        payloads.append(body)
        page_total, page_count = _page_counts(body)
        total_count = page_total if page_total is not None else len(payloads)
        if page_count <= 0:
            break
        first += bounded_size
    return payloads


def result_from_resources_payloads(
    payloads: list[Any],
    *,
    country: Country,
    source: DashboardResourceSource,
    discovered_at: datetime | None = None,
) -> DashboardResourcesResult:
    timestamp = discovered_at or datetime.now(UTC)
    rows: list[QuantumDashboardResource] = []
    total_count = 0
    for payload in payloads:
        page_total, _ = _page_counts(payload)
        if page_total is not None:
            total_count = max(total_count, page_total)
        rows.extend(
            _resources_from_payload(
                payload,
                country=country,
                source=source,
                discovered_at=timestamp,
                start_order=len(rows),
            )
        )
    resources = dedupe_dashboard_resources(rows)
    return DashboardResourcesResult(
        country=country,
        total_count=total_count or len(resources),
        resources=resources,
        from_cache=source == "cache",
        fetched_at=timestamp,
    )


def dedupe_dashboard_resources(
    resources: list[QuantumDashboardResource],
) -> list[QuantumDashboardResource]:
    by_id: dict[str, QuantumDashboardResource] = {}
    for resource in resources:
        existing = by_id.get(resource.dashboard_id)
        if existing is None:
            by_id[resource.dashboard_id] = resource
            continue
        if existing.source == "cache" and resource.source != "cache":
            by_id[resource.dashboard_id] = _merge_resource(existing, resource)
        elif not existing.name and resource.name:
            by_id[resource.dashboard_id] = _merge_resource(existing, resource)
    return sorted(by_id.values(), key=lambda item: (item.order, item.name.casefold()))


def merge_dashboard_resource_cache(
    cached: DashboardResourcesResult | None,
    fresh: DashboardResourcesResult,
) -> DashboardResourcesResult:
    if cached is None:
        return fresh
    fresh_by_id = {item.dashboard_id: item for item in fresh.resources}
    merged = list(fresh.resources)
    next_order = len(merged)
    for cached_item in cached.resources:
        if cached_item.dashboard_id in fresh_by_id:
            continue
        merged.append(
            cached_item.model_copy(
                update={
                    "source": "cache",
                    "stale": True,
                    "order": next_order,
                }
            )
        )
        next_order += 1
    return fresh.model_copy(update={"resources": merged})


def read_dashboard_resources_cache(
    country: Country | str,
    *,
    cache_dir: Path | None = None,
) -> DashboardResourcesResult | None:
    path = dashboard_resources_cache_path(Country(country), cache_dir=cache_dir)
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    result = DashboardResourcesResult.model_validate(payload)
    return result.model_copy(update={"from_cache": True})


def write_dashboard_resources_cache(
    result: DashboardResourcesResult,
    *,
    cache_dir: Path | None = None,
) -> Path:
    path = dashboard_resources_cache_path(result.country, cache_dir=cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.model_dump_json(indent=2)
    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(payload)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)
    return path


def dashboard_resources_cache_path(
    country: Country,
    *,
    cache_dir: Path | None = None,
) -> Path:
    root = cache_dir or get_settings().config_dir / "dashboard_resources"
    return root / f"{country.value}.json"


def resources_from_dashboard_configs(
    dashboards: list[Any],
    *,
    country: Country,
    source: DashboardResourceSource = "cache",
) -> DashboardResourcesResult:
    timestamp = datetime.now(UTC)
    resources = [
        QuantumDashboardResource(
            dashboard_id=str(dashboard.dashboard_id),
            name=str(dashboard.name or ""),
            type="DASHBOARD",
            starred=False,
            country=country,
            team_id=str(dashboard.team_id or "") or None,
            source=source,
            order=index,
            discovered_at=dashboard.discovered_at or timestamp,
            stale=False,
        )
        for index, dashboard in enumerate(dashboards)
        if getattr(dashboard, "dashboard_id", "")
    ]
    return DashboardResourcesResult(
        country=country,
        total_count=len(resources),
        resources=resources,
        from_cache=True,
        fetched_at=timestamp,
    )


async def _fetch_pages_with_session(
    session: Any,
    *,
    user_id: str,
    page_size: int,
) -> list[dict[str, Any]]:
    first = 0
    total_count: int | None = None
    payloads: list[dict[str, Any]] = []
    bounded_size = max(1, min(page_size, 100))
    while total_count is None or first < total_count:
        payload = resources_list_payload(user_id, first=first, size=bounded_size)
        response = await _post_graphql(session, payload)
        payloads.append(response)
        page_total, page_count = _page_counts(response)
        total_count = page_total if page_total is not None else len(payloads)
        if page_count <= 0:
            break
        first += bounded_size
    return payloads


async def _post_graphql(session: Any, payload: dict[str, Any]) -> dict[str, Any]:
    for method_name in ("post_graphql", "graphql", "post"):
        method = getattr(session, method_name, None)
        if method is None:
            continue
        if method_name == "post":
            result = method(QUANTUM_GRAPHQL_ENDPOINT, json=payload)
        else:
            result = method(QUANTUM_GRAPHQL_ENDPOINT, payload)
        if inspect.isawaitable(result):
            result = await result
        if hasattr(result, "json"):
            json_result = result.json()
            if inspect.isawaitable(json_result):
                json_result = await json_result
            result = json_result
        if isinstance(result, dict):
            return result
    raise DashboardResourcesError("No authenticated GraphQL session is available.")


async def _resolve_user_id(session: Any) -> str:
    for attribute in ("user_id", "userId", "qm_user_id"):
        value = getattr(session, attribute, None)
        value = value() if callable(value) else value
        if inspect.isawaitable(value):
            value = await value
        user_id = _text(value)
        if user_id:
            return user_id
    for attribute in ("profile", "user", "session"):
        value = getattr(session, attribute, None)
        value = value() if callable(value) else value
        if inspect.isawaitable(value):
            value = await value
        if isinstance(value, dict):
            user_id = _text(value.get("userId") or value.get("user_id") or value.get("id"))
            if user_id:
                return user_id
    raise DashboardResourcesError("No se pudo resolver userId de la sesion Quantum.")


def _resources_from_payload(
    payload: Any,
    *,
    country: Country,
    source: DashboardResourceSource,
    discovered_at: datetime,
    start_order: int,
) -> list[QuantumDashboardResource]:
    resources = _resources_container(payload)
    if not isinstance(resources, dict) or not isinstance(resources.get("resources"), list):
        return []
    rows: list[QuantumDashboardResource] = []
    for index, item in enumerate(resources["resources"]):
        if not isinstance(item, dict):
            continue
        if (_text(item.get("type")) or "").upper() != "DASHBOARD":
            continue
        dashboard_id = _text(item.get("id") or item.get("dashboardId"))
        if not dashboard_id:
            continue
        rows.append(
            QuantumDashboardResource(
                dashboard_id=dashboard_id,
                name=_text(item.get("name") or item.get("title")) or "",
                type="DASHBOARD",
                starred=bool(item.get("starred")),
                country=country,
                team_id=_text(item.get("teamID") or item.get("teamId") or item.get("team_id")),
                source=source,
                order=start_order + index,
                discovered_at=discovered_at,
            )
        )
    return rows


def _resources_container(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    resources = payload.get("resources")
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("resources"), dict):
        resources = data["resources"]
    return cast(dict[str, Any], resources) if isinstance(resources, dict) else None


def _page_counts(payload: Any) -> tuple[int | None, int]:
    resources = _resources_container(payload)
    if not resources:
        return None, 0
    total_count = resources.get("totalCount")
    page = resources.get("resources")
    return (
        int(total_count) if isinstance(total_count, int | float | str) else None,
        len(page) if isinstance(page, list) else 0,
    )


def _merge_resource(
    existing: QuantumDashboardResource,
    incoming: QuantumDashboardResource,
) -> QuantumDashboardResource:
    return incoming.model_copy(
        update={
            "team_id": incoming.team_id or existing.team_id,
            "starred": incoming.starred or existing.starred,
        }
    )


def _session_cache_dir(session: Any) -> Path | None:
    value = getattr(session, "dashboard_resources_cache_dir", None) or getattr(
        session, "cache_dir", None
    )
    if value is None:
        return None
    return Path(value)


def result_from_resource_rows(
    rows: list[QuantumDashboardResource],
    *,
    country: Country,
    fetched_at: datetime | None = None,
    from_cache: bool = False,
) -> DashboardResourcesResult:
    return DashboardResourcesResult(
        country=country,
        total_count=len(rows),
        resources=dedupe_dashboard_resources(rows),
        from_cache=from_cache,
        fetched_at=fetched_at or datetime.now(UTC),
    )


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
