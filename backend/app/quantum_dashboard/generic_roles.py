from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field

GENERIC_ROLE_PREFIX = "generic."
GENERIC_WIDGET_TYPES = {"CHART", "TABLE", "DONUT", "KPI"}


class DashboardTabResolution(BaseModel):
    status: Literal["resolved", "unassigned", "ambiguous"]
    tab: str | None = None
    tab_id: str | None = None
    tab_index: int | None = None
    evidence: list[str] = Field(default_factory=list)


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


def dashboard_tab_for_widget(
    tab: str | None,
    tab_name: str | None,
    title: str | None = None,
    *,
    tab_id: str | None = None,
    tab_index: int | None = None,
) -> DashboardTabResolution:
    del title
    explicit_tab = _safe_text(tab)
    explicit_name = _safe_text(tab_name)
    if explicit_tab and explicit_name:
        return DashboardTabResolution(
            status="resolved",
            tab=explicit_tab,
            tab_id=_safe_text(tab_id),
            tab_index=tab_index,
            evidence=["explicit_tab", "explicit_tab_name"],
        )
    if explicit_tab or explicit_name or tab_id is not None or tab_index is not None:
        return DashboardTabResolution(
            status="resolved",
            tab=explicit_tab or explicit_name or f"tab-{tab_index or 0}",
            tab_id=_safe_text(tab_id),
            tab_index=tab_index,
            evidence=["partial_explicit_tab_contract"],
        )
    return DashboardTabResolution(
        status="unassigned",
        tab="unassigned",
        tab_id=None,
        tab_index=None,
        evidence=["missing_tab_contract"],
    )


def _safe_token(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    token = re.sub(r"[^A-Za-z0-9_-]+", "_", normalized.strip())
    return token.strip("_") or "unknown"


def _safe_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
