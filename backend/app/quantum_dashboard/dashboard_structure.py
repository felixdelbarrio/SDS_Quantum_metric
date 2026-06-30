from __future__ import annotations

import unicodedata
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.app.quantum.schemas import (
    Country,
    QuantumDashboardConfig,
    QuantumDashboardTabConfig,
    QuantumWidgetConfig,
)
from backend.app.quantum_dashboard.card_mapper import map_card_role
from backend.app.quantum_dashboard.catalog import spec_for_role

StructureSource = Literal["quantum_api", "quantum_web", "config_cache"]
WidgetKind = Literal["chart", "table", "donut", "unknown"]


class QuantumDashboardTab(BaseModel):
    tab_id: str | None = None
    tab_index: int
    name: str
    normalized_role: str | None = None


class QuantumDashboardWidget(BaseModel):
    widget_id: str
    card_id: str | None = None
    title: str
    tab_name: str
    tab_index: int
    visual_role: str | None = None
    widget_type: WidgetKind = "unknown"
    enabled: bool = True
    required: bool = False
    supported: bool = False
    source: StructureSource


class QuantumDashboardStructure(BaseModel):
    country: Country
    dashboard_id: str
    team_id: str | None = None
    source: StructureSource
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    tabs: list[QuantumDashboardTab] = Field(default_factory=list)
    widgets: list[QuantumDashboardWidget] = Field(default_factory=list)


async def discover_dashboard_structure(
    country: Country,
    dashboard_id: str,
    team_id: str | None,
    session: Any,
) -> QuantumDashboardStructure:
    payloads = []
    for attribute in ("structure_payloads", "dashboard_payloads", "payloads"):
        value = getattr(session, attribute, None)
        if value is None:
            continue
        result = value() if callable(value) else value
        if hasattr(result, "__await__"):
            result = await result
        if isinstance(result, list):
            payloads = result
            break
    structure = structure_from_payloads(
        payloads,
        country=country,
        dashboard_id=dashboard_id,
        team_id=team_id,
        source="quantum_api",
    )
    if structure.widgets or structure.tabs:
        return structure
    cache = getattr(session, "dashboard_config", None)
    if isinstance(cache, QuantumDashboardConfig):
        return structure_from_dashboard_config(country, cache)
    return structure


def structure_from_payloads(
    payloads: list[Any],
    *,
    country: Country,
    dashboard_id: str,
    team_id: str | None,
    source: StructureSource,
) -> QuantumDashboardStructure:
    tabs: list[QuantumDashboardTab] = []
    widgets: list[QuantumDashboardWidget] = []
    for payload in payloads:
        _extract_structure(
            payload,
            tabs=tabs,
            widgets=widgets,
            source=source,
            tab_context=None,
            path=(),
        )
    return QuantumDashboardStructure(
        country=country,
        dashboard_id=dashboard_id,
        team_id=team_id,
        source=source,
        tabs=_dedupe_tabs(tabs),
        widgets=_dedupe_widgets(widgets),
    )


def structure_from_dashboard_config(
    country: Country,
    dashboard: QuantumDashboardConfig,
) -> QuantumDashboardStructure:
    tabs = [
        QuantumDashboardTab(
            tab_id=tab.tab_id,
            tab_index=tab.tab_index,
            name=tab.name,
            normalized_role=tab.normalized_role,
        )
        for tab in dashboard.tabs
    ]
    if not tabs:
        tabs = _dedupe_tabs(
            [
                QuantumDashboardTab(
                    tab_index=widget.tab_index,
                    name=widget.tab_name or widget.tab,
                    normalized_role=widget.tab if widget.tab in {"summary", "errors"} else None,
                )
                for widget in dashboard.widgets
            ]
        )
    widgets = [
        QuantumDashboardWidget(
            widget_id=widget.widget_id or widget.card_id or widget.role,
            card_id=widget.card_id or widget.widget_id or None,
            title=widget.title or widget.role,
            tab_name=widget.tab_name or widget.tab,
            tab_index=widget.tab_index,
            visual_role=widget.role or None,
            widget_type=_to_widget_kind(widget.widget_type),
            enabled=widget.enabled,
            required=widget.required,
            supported=widget.supported and bool(widget.role and spec_for_role(widget.role)),
            source=widget.source,
        )
        for widget in dashboard.widgets
    ]
    return QuantumDashboardStructure(
        country=country,
        dashboard_id=dashboard.dashboard_id,
        team_id=dashboard.team_id or None,
        source="config_cache",
        discovered_at=dashboard.last_structure_at or dashboard.discovered_at or datetime.now(UTC),
        tabs=tabs,
        widgets=widgets,
    )


def widget_configs_from_structure(
    structure: QuantumDashboardStructure,
    existing: list[QuantumWidgetConfig] | None = None,
) -> list[QuantumWidgetConfig]:
    enabled_by_key = {
        _widget_key(widget.role, widget.widget_id, widget.card_id): widget.enabled
        for widget in existing or []
    }
    configs: list[QuantumWidgetConfig] = []
    for widget in structure.widgets:
        role = widget.visual_role or ""
        key = _widget_key(role, widget.widget_id, widget.card_id)
        widget_type = _to_config_widget_type(widget.widget_type)
        supported = bool(role and spec_for_role(role))
        configs.append(
            QuantumWidgetConfig(
                role=role,
                title=widget.title,
                widget_id=widget.widget_id,
                card_id=widget.card_id,
                widget_type=widget_type,
                tab=_normalized_tab(structure.tabs, widget.tab_index, widget.tab_name),
                tab_name=widget.tab_name,
                tab_index=widget.tab_index,
                enabled=enabled_by_key.get(key, widget.enabled and supported),
                required=supported,
                supported=supported,
                source=widget.source,
                discovered_at=structure.discovered_at,
            )
        )
    return configs


def tab_configs_from_structure(
    structure: QuantumDashboardStructure,
) -> list[QuantumDashboardTabConfig]:
    return [
        QuantumDashboardTabConfig(
            tab_id=tab.tab_id,
            tab_index=tab.tab_index,
            name=tab.name,
            normalized_role=tab.normalized_role,
        )
        for tab in structure.tabs
    ]


def _extract_structure(
    value: Any,
    *,
    tabs: list[QuantumDashboardTab],
    widgets: list[QuantumDashboardWidget],
    source: StructureSource,
    tab_context: QuantumDashboardTab | None,
    path: tuple[str, ...],
) -> None:
    if isinstance(value, list):
        for item in value:
            _extract_structure(
                item,
                tabs=tabs,
                widgets=widgets,
                source=source,
                tab_context=tab_context,
                path=path,
            )
        return
    if not isinstance(value, dict):
        return

    current_tab = _tab_from_candidate(value, path) or tab_context
    if current_tab is not None:
        tabs.append(current_tab)

    widget = _widget_from_candidate(value, source, current_tab)
    if widget is not None:
        widgets.append(widget)

    for key, child in value.items():
        _extract_structure(
            child,
            tabs=tabs,
            widgets=widgets,
            source=source,
            tab_context=current_tab,
            path=(*path, str(key)),
        )


def _tab_from_candidate(
    item: dict[str, Any],
    path: tuple[str, ...],
) -> QuantumDashboardTab | None:
    if not _is_tab_path(path) and not any(key in item for key in ("tabIndex", "tab_index")):
        return None
    name = _text(item.get("name") or item.get("tabName") or item.get("title") or item.get("label"))
    if not name:
        return None
    index = _int(item.get("tabIndex") or item.get("tab_index") or item.get("index"), 0)
    return QuantumDashboardTab(
        tab_id=_text(item.get("tabId") or item.get("tab_id") or item.get("id")),
        tab_index=index,
        name=name,
        normalized_role=_normalized_role(name),
    )


def _widget_from_candidate(
    item: dict[str, Any],
    source: StructureSource,
    tab_context: QuantumDashboardTab | None,
) -> QuantumDashboardWidget | None:
    card_id = _text(item.get("cardId") or item.get("card_id"))
    widget_id = _text(
        item.get("widgetId")
        or item.get("widget_id")
        or item.get("cardId")
        or item.get("card_id")
        or item.get("id")
    )
    title = _text(item.get("cardTitle") or item.get("title") or item.get("name"))
    if not widget_id or not title:
        return None
    if _text(item.get("dashboardId") or item.get("dashboard_id")) and not card_id:
        return None
    tab_name = _text(item.get("tabName") or item.get("tab_name")) or (
        tab_context.name if tab_context is not None else "Tab"
    )
    tab_index = _int(
        item.get("tabIndex") or item.get("tab_index"),
        tab_context.tab_index if tab_context is not None else 0,
    )
    raw_type = _text(
        item.get("cardType")
        or item.get("card_type")
        or item.get("widgetType")
        or item.get("widget_type")
        or item.get("visualizationType")
        or item.get("type")
    )
    kind = _to_widget_kind(raw_type)
    tab_role = (
        tab_context.normalized_role if tab_context is not None else _normalized_role(tab_name)
    )
    mapped_role = map_card_role(
        {
            "card_title": title,
            "card_type": "DONUT" if kind == "donut" else kind.upper(),
            "tab": tab_role,
        }
    )
    role: str | None = str(mapped_role) if mapped_role is not None else None
    if tab_role == "errors" and (role is None or role.startswith("summary.")):
        role = _errors_role_from_title(title, kind) or role
    return QuantumDashboardWidget(
        widget_id=widget_id,
        card_id=card_id,
        title=title,
        tab_name=tab_name,
        tab_index=tab_index,
        visual_role=role,
        widget_type=kind,
        enabled=bool(role),
        required=bool(role and spec_for_role(role)),
        supported=bool(role and spec_for_role(role)),
        source=source,
    )


def _dedupe_tabs(tabs: list[QuantumDashboardTab]) -> list[QuantumDashboardTab]:
    by_key: dict[tuple[int, str], QuantumDashboardTab] = {}
    for tab in tabs:
        by_key.setdefault((tab.tab_index, tab.name), tab)
    return sorted(by_key.values(), key=lambda tab: (tab.tab_index, tab.name.casefold()))


def _dedupe_widgets(widgets: list[QuantumDashboardWidget]) -> list[QuantumDashboardWidget]:
    by_key: dict[str, QuantumDashboardWidget] = {}
    for widget in widgets:
        by_key.setdefault(widget.widget_id, widget)
    return sorted(by_key.values(), key=lambda widget: (widget.tab_index, widget.title.casefold()))


def _normalized_tab(
    tabs: list[QuantumDashboardTab],
    tab_index: int,
    tab_name: str,
) -> str:
    for tab in tabs:
        if tab.tab_index == tab_index:
            return tab.normalized_role or _slug(tab.name)
    return _normalized_role(tab_name) or _slug(tab_name)


def _normalized_role(name: str) -> str | None:
    canonical = _slug(name)
    if canonical in {"resumen", "summary"}:
        return "summary"
    if canonical in {"errores", "errors"}:
        return "errors"
    return None


def _errors_role_from_title(title: str, kind: WidgetKind) -> str | None:
    canonical = _slug(title)
    if "comparativa" in canonical and "app" in canonical:
        return "errors.error_sessions_by_app_name_comparison"
    if "percent" in canonical and "app" in canonical:
        return "errors.error_session_percentage_by_app_name"
    if "top" in canonical and "error" in canonical:
        return "errors.top_errors_by_error_name"
    if "evolutivo" in canonical or (kind == "chart" and "error" in canonical):
        return "errors.error_sessions_percentage_evolution"
    return None


def _to_widget_kind(value: str | None) -> WidgetKind:
    canonical = _slug(value or "")
    if "donut" in canonical or "pie" in canonical:
        return "donut"
    if "table" in canonical or "tabla" in canonical:
        return "table"
    if "chart" in canonical or "line" in canonical or "bar" in canonical or "kpi" in canonical:
        return "chart"
    return "unknown"


def _to_config_widget_type(
    kind: WidgetKind,
) -> Literal["CHART", "TABLE", "DONUT", "KPI", "UNKNOWN"]:
    if kind == "donut":
        return "DONUT"
    if kind == "table":
        return "TABLE"
    if kind == "chart":
        return "CHART"
    return "UNKNOWN"


def _widget_key(role: str, widget_id: str, card_id: str | None) -> str:
    return role or card_id or widget_id


def _is_tab_path(path: tuple[str, ...]) -> bool:
    return bool(path and path[-1].casefold() in {"tabs", "dashboardtabs", "dashboard_tabs"})


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return normalized.replace("%", "percent").replace("_", " ").strip().casefold()


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
