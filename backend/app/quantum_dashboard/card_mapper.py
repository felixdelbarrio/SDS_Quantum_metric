from __future__ import annotations

import json
import unicodedata
from typing import Any

from backend.app.quantum_dashboard.catalog import (
    ERRORS_APP_COMPARISON,
    ERRORS_APP_PERCENTAGE,
    ERRORS_EVOLUTION,
    ERRORS_TOP_ERRORS,
    SUMMARY_AVG_SESSION_DURATION,
    SUMMARY_CONVERTED_SESSIONS,
    SUMMARY_DETAIL_TABLE,
    SUMMARY_PAGE_VIEWS,
    SUMMARY_SESSIONS,
    spec_for_role,
)
from backend.app.quantum_dashboard.models import VisualRole

TITLE_KEYWORDS: tuple[tuple[VisualRole, tuple[str, ...]], ...] = (
    (SUMMARY_PAGE_VIEWS, ("paginas vistas", "page views")),
    (SUMMARY_CONVERTED_SESSIONS, ("sesiones con conversion", "conversiones", "converted")),
    (SUMMARY_AVG_SESSION_DURATION, ("tiempo medio", "average session", "avg session")),
    (SUMMARY_DETAIL_TABLE, ("detalle por app", "app name y sistema", "operating system")),
    (SUMMARY_SESSIONS, ("sesiones", "sessions")),
    (ERRORS_TOP_ERRORS, ("top 10 errores", "nombre del error", "error name")),
    (ERRORS_APP_COMPARISON, ("comparativa", "sesiones con error por app", "donut")),
    (ERRORS_APP_PERCENTAGE, ("% sesiones con error por app", "error por app name")),
    (ERRORS_EVOLUTION, ("evolutivo", "% sesiones con error", "error sessions percentage")),
)

METRIC_HINTS: tuple[tuple[VisualRole, tuple[str, ...]], ...] = (
    (SUMMARY_PAGE_VIEWS, ("page_views", "pageviews")),
    (SUMMARY_CONVERTED_SESSIONS, ("converted_sessions", "conversion", "conversiones")),
    (SUMMARY_AVG_SESSION_DURATION, ("avg_session", "session_duration", "tiempo_medio")),
    (ERRORS_EVOLUTION, ("error_session_percent", "sessions_with_error_percent")),
    (ERRORS_TOP_ERRORS, ("error_name", "errors_by_name")),
    (ERRORS_APP_COMPARISON, ("sessions_with_error", "app_name")),
    (ERRORS_APP_PERCENTAGE, ("error_session_percent", "app_name")),
    (SUMMARY_SESSIONS, ("sessions", "sesiones")),
)

REAL_SUMMARY_METRIC_IDS: dict[str, VisualRole] = {
    "bde22d61-91c0-4d27-8ee3-ef467daea00c": SUMMARY_PAGE_VIEWS,
    "081453e2-dd2a-4479-8ff7-e05825869645": SUMMARY_SESSIONS,
    "bd53548d-16f7-49f2-af09-ee3f801e62c4": SUMMARY_CONVERTED_SESSIONS,
    "62597b63-d0a4-4d50-8f20-20083bfaf941": SUMMARY_CONVERTED_SESSIONS,
    "2249fa52-8d15-46f4-b601-fc6d11958218": SUMMARY_AVG_SESSION_DURATION,
}

REAL_ERRORS_METRIC_IDS: dict[str, VisualRole] = {
    "519433db-1b8e-4989-ab29-6eca4492cf94": ERRORS_TOP_ERRORS,
    "d450b2fd-26d7-4a9e-a076-199a9d51e1bb": ERRORS_APP_COMPARISON,
}


def map_card_role(call: dict[str, Any]) -> VisualRole | None:
    explicit = _text(call.get("card_role") or call.get("visual_role"))
    if explicit and spec_for_role(explicit):
        return explicit  # type: ignore[return-value]

    request_json = _parse_json(call.get("request_json"))
    response_json = _parse_json(call.get("response_json"))
    metadata = _metadata(request_json)
    metadata_role = _text(metadata.get("cardRole") or metadata.get("visualRole"))
    if metadata_role and spec_for_role(metadata_role):
        return metadata_role  # type: ignore[return-value]

    title = " ".join(
        value
        for value in (
            _text(call.get("card_title")),
            _text(metadata.get("cardTitle")),
            _text(metadata.get("title")),
            _text(call.get("view_name")),
        )
        if value
    )
    role_from_title = _match_title(title)
    if role_from_title:
        return role_from_title

    tab = _text(call.get("tab"))
    card_type = _text(call.get("card_type"))
    view_name = _text(call.get("view_name")) or ""
    if view_name in {"navbarMetricsQuery", "dashboardReplayQuery"}:
        return None
    metric_ids = _metric_ids(call.get("metric_ids"), metadata.get("metricIds"))
    dimension_paths = _dimension_paths(request_json)

    if tab == "summary" and card_type == "TABLE":
        return SUMMARY_DETAIL_TABLE
    if tab == "summary":
        for metric_id in metric_ids:
            role = REAL_SUMMARY_METRIC_IDS.get(metric_id)
            if role:
                return role
        role = _summary_role_from_metric_shape(request_json)
        if role:
            return role

    if tab == "errors":
        if card_type == "TABLE":
            if view_name == "coreMetrics" and not metric_ids and not dimension_paths:
                return None
            if any(path and path[-1] == "event" for path in dimension_paths):
                return ERRORS_TOP_ERRORS
            if any("mde_value" in path for path in dimension_paths):
                return ERRORS_APP_PERCENTAGE
            if "topN" in view_name or len(metric_ids) > 1:
                return ERRORS_TOP_ERRORS
            return ERRORS_APP_PERCENTAGE
        if card_type == "CHART":
            if any("mde_value" in path for path in dimension_paths):
                return ERRORS_APP_COMPARISON
            if any(
                REAL_ERRORS_METRIC_IDS.get(metric_id) == ERRORS_APP_COMPARISON
                for metric_id in metric_ids
            ):
                return ERRORS_APP_COMPARISON
            if any(
                REAL_ERRORS_METRIC_IDS.get(metric_id) == ERRORS_TOP_ERRORS
                for metric_id in metric_ids
            ):
                return ERRORS_EVOLUTION
            return None

    haystack = _canonical(
        " ".join(
            [
                json.dumps(metadata, ensure_ascii=False, default=str),
                json.dumps(response_json.get("columns", ""), ensure_ascii=False, default=str),
                _text(call.get("metric_ids")) or "",
            ]
        )
    )
    for role, hints in METRIC_HINTS:
        if all(_canonical(hint) in haystack for hint in hints):
            return role
    return None


def card_title_for_role(role: VisualRole, call: dict[str, Any]) -> str:
    request_json = _parse_json(call.get("request_json"))
    metadata = _metadata(request_json)
    spec = spec_for_role(role)
    return (
        _text(call.get("card_title"))
        or _text(metadata.get("cardTitle"))
        or _text(metadata.get("title"))
        or (spec.title if spec else str(role))
    )


def _match_title(title: str) -> VisualRole | None:
    canonical = _canonical(title)
    for role, keywords in TITLE_KEYWORDS:
        if any(keyword in canonical for keyword in keywords):
            return role
    return None


def _metadata(request_json: dict[str, Any]) -> dict[str, Any]:
    query = request_json.get("query")
    container = query if isinstance(query, dict) else request_json
    metadata = container.get("metadata") if isinstance(container, dict) else None
    return metadata if isinstance(metadata, dict) else {}


def _parse_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _metric_ids(raw_value: Any, metadata_value: Any) -> list[str]:
    value = raw_value if raw_value not in (None, "", "[]") else metadata_value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
        return [str(parsed)]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _dimension_paths(request_json: dict[str, Any]) -> list[list[str]]:
    query = request_json.get("query")
    container = query if isinstance(query, dict) else request_json
    dimensions = container.get("dimensions") if isinstance(container, dict) else None
    items = dimensions.get("dimensions") if isinstance(dimensions, dict) else None
    if not isinstance(items, list):
        return []
    paths: list[list[str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        if isinstance(path, list):
            paths.append([str(part) for part in path])
    return paths


def _summary_role_from_metric_shape(request_json: dict[str, Any]) -> VisualRole | None:
    query = request_json.get("query")
    container = query if isinstance(query, dict) else request_json
    metrics = container.get("metrics") if isinstance(container, dict) else None
    if not metrics:
        return None
    paths = _paths(metrics)
    metric_text = _canonical(json.dumps(metrics, ensure_ascii=False, default=str))
    if ("session", "total_engaged_seconds") in paths:
        return SUMMARY_AVG_SESSION_DURATION
    if ("hit", "id") in paths:
        return SUMMARY_PAGE_VIEWS
    if ("session", "id") in paths:
        if "pagina exitosa" in metric_text:
            return SUMMARY_CONVERTED_SESSIONS
        return SUMMARY_SESSIONS
    return None


def _paths(value: Any) -> set[tuple[str, ...]]:
    paths: set[tuple[str, ...]] = set()
    if isinstance(value, dict):
        path = value.get("path")
        if isinstance(path, list):
            paths.add(tuple(str(part) for part in path))
        for child in value.values():
            paths.update(_paths(child))
    elif isinstance(value, list):
        for item in value:
            paths.update(_paths(item))
    return paths


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _canonical(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return normalized.replace("%", " percent ").replace("_", " ").casefold()
