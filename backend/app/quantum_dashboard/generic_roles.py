from __future__ import annotations

import re
import unicodedata
from typing import Any

GENERIC_ROLE_PREFIX = "generic."
GENERIC_WIDGET_TYPES = {"CHART", "TABLE", "DONUT", "KPI"}


def is_generic_role(role: str | None) -> bool:
    return bool(role and role.startswith(GENERIC_ROLE_PREFIX))


def is_supported_generic_widget_type(widget_type: str | None) -> bool:
    return normalized_widget_type(widget_type) in GENERIC_WIDGET_TYPES


def normalized_widget_type(widget_type: str | None) -> str:
    raw = str(widget_type or "").strip().upper()
    if raw in GENERIC_WIDGET_TYPES:
        return raw
    if "DONUT" in raw or "PIE" in raw:
        return "DONUT"
    if "TABLE" in raw or "TABLA" in raw:
        return "TABLE"
    if "KPI" in raw:
        return "KPI"
    if "CHART" in raw or "LINE" in raw or "BAR" in raw:
        return "CHART"
    return "UNKNOWN"


def generic_role_for_widget(
    *,
    widget_id: str | None,
    card_id: str | None,
    widget_type: str | None,
    tab_index: int | None = None,
) -> str:
    kind = normalized_widget_type(widget_type).lower()
    identity = _safe_token(widget_id or card_id or "unknown")
    tab = max(0, int(tab_index or 0))
    return f"{GENERIC_ROLE_PREFIX}{tab}.{kind}.{identity}"


def generic_kind_from_role(role: str | None) -> str | None:
    if not is_generic_role(role):
        return None
    parts = str(role).split(".")
    return parts[2].upper() if len(parts) >= 4 else None


def dashboard_tab_for_widget(tab: str | None, tab_name: str | None, title: str | None) -> str:
    explicit_tab = _canonical(tab or "")
    if "summary" in explicit_tab or "resumen" in explicit_tab:
        return "summary"
    if "error" in explicit_tab or "errores" in explicit_tab:
        return "errors"

    haystack = _canonical(" ".join(str(item or "") for item in (tab_name, title)))
    if "summary" in haystack or "resumen" in haystack:
        return "summary"
    if "error" in haystack or "errores" in haystack:
        return "errors"
    return "summary"


def infer_generic_unit(title: str | None, value: Any = None) -> str:
    canonical = _canonical(title or "")
    if any(
        token in canonical
        for token in (
            "%",
            " percent ",
            "percentage",
            "porcentaje",
            " rate",
            "ratio",
            "success",
            "conversion",
            " cr ",
        )
    ):
        return "percent"
    numeric = _number(value)
    if numeric is not None and 0 <= abs(numeric) <= 1 and "score" not in canonical:
        return "percent"
    return "count"


def _safe_token(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    token = re.sub(r"[^A-Za-z0-9_-]+", "_", normalized.strip())
    return token.strip("_") or "unknown"


def _canonical(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return f" {normalized.replace('_', ' ').casefold()} "


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None
