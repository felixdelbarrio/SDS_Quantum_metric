from __future__ import annotations

import hashlib
import json
import time
import unicodedata
from datetime import UTC, datetime
from typing import Any, Literal, cast
from urllib.parse import urlencode, urlparse, urlunparse

from pydantic import BaseModel, Field

from backend.app.auth.browser_cookies import BrowserCookie
from backend.app.config.settings import Settings
from backend.app.ingestion.capture import (
    _configure_playwright_browser_path,
    _launch_headless_browser,
    _looks_unauthenticated,
)
from backend.app.observability.sanitizer import sanitize_error
from backend.app.quantum.schemas import (
    Country,
    QuantumDashboardConfig,
    QuantumDashboardSectionConfig,
    QuantumDashboardTabConfig,
    QuantumWidgetConfig,
)
from backend.app.quantum_dashboard.card_mapper import map_card_role
from backend.app.quantum_dashboard.dashboard_resources import QUANTUM_GRAPHQL_ENDPOINT
from backend.app.quantum_dashboard.generic_roles import (
    generic_role_for_widget,
    is_supported_generic_widget_type,
)
from backend.app.quantum_dashboard.widget_support import assess_widget_support

StructureSource = Literal["quantum_api", "quantum_web", "config_cache"]
WidgetKind = Literal["chart", "table", "donut", "unknown"]
LOAD_DASHBOARD_QUERY = """
    query LoadDashboard($dashboardId: ID!) {
        resource(id: $dashboardId) {
            id
            starred
            entity {
                ... on Dashboard {
                    id
                    title
                    description
                    config
                    json
                    tabs
                    cards {
                        id
                        title
                        description
                        json
                    }
                    highestAccessLevel
                    version
                }
            }
        }
    }
"""


class QuantumDashboardTab(BaseModel):
    tab_id: str | None = None
    tab_index: int
    name: str
    normalized_role: str | None = None


class QuantumDashboardSection(BaseModel):
    section_id: str | None = None
    tab_id: str | None = None
    tab_index: int
    name: str
    section_index: int


class QuantumDashboardWidget(BaseModel):
    widget_id: str
    card_id: str | None = None
    title: str
    tab_id: str | None = None
    tab_name: str
    tab_index: int
    section_id: str | None = None
    section_name: str | None = None
    section_index: int | None = None
    widget_order: int | None = None
    layout_x: int | None = None
    layout_y: int | None = None
    layout_width: int | None = None
    layout_height: int | None = None
    visual_contract: dict[str, Any] = Field(default_factory=dict)
    visual_role: str | None = None
    widget_type: WidgetKind = "unknown"
    enabled: bool = True
    required: bool = False
    supported: bool = False
    source: StructureSource


class QuantumDashboardStructure(BaseModel):
    country: Country
    dashboard_id: str
    dashboard_name: str | None = None
    team_id: str | None = None
    source: StructureSource
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    tabs: list[QuantumDashboardTab] = Field(default_factory=list)
    sections: list[QuantumDashboardSection] = Field(default_factory=list)
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
    sections: list[QuantumDashboardSection] = []
    widgets: list[QuantumDashboardWidget] = []
    dashboard_name: str | None = None
    for payload in payloads:
        dashboard_name = dashboard_name or _dashboard_name_from_payload(payload)
        _extract_structure(
            payload,
            tabs=tabs,
            sections=sections,
            widgets=widgets,
            source=source,
            tab_context=None,
            section_context=None,
            path=(),
        )
    return QuantumDashboardStructure(
        country=country,
        dashboard_id=dashboard_id,
        dashboard_name=dashboard_name,
        team_id=team_id,
        source=source,
        tabs=_dedupe_tabs(tabs),
        sections=_dedupe_sections(sections),
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
    sections = [
        QuantumDashboardSection(
            section_id=section.section_id,
            tab_id=section.tab_id,
            tab_index=section.tab_index,
            name=section.name,
            section_index=section.section_index,
        )
        for section in dashboard.sections
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
            tab_id=widget.tab_id,
            tab_name=widget.tab_name or widget.tab,
            tab_index=widget.tab_index,
            section_id=widget.section_id,
            section_name=widget.section_name,
            section_index=widget.section_index,
            visual_role=widget.role or None,
            widget_type=_to_widget_kind(widget.widget_type),
            enabled=widget.enabled,
            required=widget.required,
            supported=widget.supported
            and assess_widget_support(
                widget_id=widget.widget_id or widget.card_id or widget.role,
                title=widget.title or widget.role,
                widget_type=widget.widget_type,
                visual_role=widget.role or None,
            ).supported,
            widget_order=widget.widget_order,
            layout_x=widget.layout_x,
            layout_y=widget.layout_y,
            layout_width=widget.layout_width,
            layout_height=widget.layout_height,
            visual_contract=widget.visual_contract,
            source=widget.source,
        )
        for widget in dashboard.widgets
    ]
    return QuantumDashboardStructure(
        country=country,
        dashboard_id=dashboard.dashboard_id,
        dashboard_name=dashboard.name or None,
        team_id=dashboard.team_id or None,
        source="config_cache",
        discovered_at=dashboard.last_structure_at or dashboard.discovered_at or datetime.now(UTC),
        tabs=tabs,
        sections=sections,
        widgets=widgets,
    )


def discover_dashboard_structure_via_browser(
    *,
    settings: Settings,
    cookies: list[BrowserCookie],
    country: Country,
    base_url: str,
    dashboard_id: str,
    team_id: str | None,
    wait_seconds: int,
) -> tuple[QuantumDashboardStructure, str | None]:
    _configure_playwright_browser_path()
    from playwright.sync_api import sync_playwright

    payloads: list[Any] = []
    query_headers_ref: dict[str, dict[str, str] | None] = {"value": None}
    error: str | None = None
    with sync_playwright() as playwright:
        context: Any | None = None
        browser: Any | None = None
        try:
            browser = _launch_headless_browser(playwright, settings)
            context = browser.new_context(ignore_https_errors=not settings.qm_verify_tls)
            if cookies:
                context.add_cookies(cast(Any, [cookie.as_playwright() for cookie in cookies]))

            page = context.new_page()
            page.on("request", lambda request: _capture_query_headers(request, query_headers_ref))
            page.on(
                "response",
                lambda response: _collect_load_dashboard_payload(
                    response,
                    payloads,
                    dashboard_id,
                ),
            )
            page.goto(
                _dashboard_url(base_url, dashboard_id, team_id),
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            _wait_for_structure_payload(page, payloads, wait_seconds)
            if not payloads and query_headers_ref.get("value"):
                response = context.request.post(
                    QUANTUM_GRAPHQL_ENDPOINT,
                    headers=cast(dict[str, str], query_headers_ref["value"]),
                    data=_load_dashboard_payload(dashboard_id),
                    timeout=60_000,
                )
                if response.ok:
                    payloads.append(response.json())
            if not payloads and _looks_unauthenticated(page):
                error = "Quantum Web redirected to an authentication page."
            elif not payloads:
                error = "Quantum Web did not expose a LoadDashboard response."
            page.close()
        except Exception as exc:
            error = sanitize_error(exc)
        finally:
            if context is not None:
                context.close()
            if browser is not None:
                browser.close()

    return (
        structure_from_payloads(
            payloads,
            country=country,
            dashboard_id=dashboard_id,
            team_id=team_id,
            source="quantum_web",
        ),
        error,
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
        widget_type = _to_config_widget_type(widget.widget_type)
        role = widget.visual_role or (
            generic_role_for_widget(
                widget_id=widget.widget_id,
                card_id=widget.card_id,
                widget_type=widget_type,
                tab_index=widget.tab_index,
            )
            if is_supported_generic_widget_type(widget_type)
            else ""
        )
        key = _widget_key(role, widget.widget_id, widget.card_id)
        supported = assess_widget_support(
            widget_id=widget.widget_id,
            title=widget.title,
            widget_type=widget_type,
            visual_role=role,
        ).supported
        configs.append(
            QuantumWidgetConfig(
                role=role,
                title=widget.title,
                widget_id=widget.widget_id,
                card_id=widget.card_id,
                widget_type=widget_type,
                tab_id=widget.tab_id,
                tab=_normalized_tab(structure.tabs, widget.tab_index, widget.tab_name),
                tab_name=widget.tab_name,
                tab_index=widget.tab_index,
                tab_resolution="resolved" if widget.tab_id or widget.tab_name else "unassigned",
                section_id=widget.section_id,
                section_name=widget.section_name,
                section_index=widget.section_index,
                widget_order=(
                    widget.widget_order if widget.widget_order is not None else len(configs)
                ),
                layout_x=widget.layout_x,
                layout_y=widget.layout_y,
                layout_width=widget.layout_width,
                layout_height=widget.layout_height,
                query_fingerprint=_text(
                    widget.visual_contract.get("query", {}).get("fingerprint")
                    if isinstance(widget.visual_contract.get("query"), dict)
                    else None
                ),
                visual_contract=widget.visual_contract,
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


def section_configs_from_structure(
    structure: QuantumDashboardStructure,
) -> list[QuantumDashboardSectionConfig]:
    return [
        QuantumDashboardSectionConfig(
            section_id=section.section_id,
            tab_id=section.tab_id,
            tab_index=section.tab_index,
            name=section.name,
            section_index=section.section_index,
        )
        for section in structure.sections
    ]


def dashboard_config_from_structure(
    dashboard: QuantumDashboardConfig,
    structure: QuantumDashboardStructure,
    *,
    timezone: str,
) -> QuantumDashboardConfig:
    return dashboard.model_copy(
        update={
            "name": structure.dashboard_name or dashboard.name,
            "team_id": structure.team_id or dashboard.team_id,
            "summary_tab": _tab_index_for_role(structure.tabs, "summary", dashboard.summary_tab),
            "errors_tab": _tab_index_for_role(structure.tabs, "errors", dashboard.errors_tab),
            "timezone": dashboard.timezone or timezone,
            "source": structure.source,
            "last_structure_at": structure.discovered_at,
            "tabs": tab_configs_from_structure(structure),
            "sections": section_configs_from_structure(structure),
            "widgets": widget_configs_from_structure(structure, dashboard.widgets),
        }
    )


def _tab_index_for_role(
    tabs: list[QuantumDashboardTab],
    role: str,
    fallback: int,
) -> int:
    return next(
        (tab.tab_index for tab in tabs if tab.normalized_role == role),
        fallback,
    )


def _extract_structure(
    value: Any,
    *,
    tabs: list[QuantumDashboardTab],
    sections: list[QuantumDashboardSection],
    widgets: list[QuantumDashboardWidget],
    source: StructureSource,
    tab_context: QuantumDashboardTab | None,
    section_context: QuantumDashboardSection | None,
    path: tuple[str, ...],
) -> None:
    if isinstance(value, list):
        for index, item in enumerate(value):
            child = item
            if (
                isinstance(item, dict)
                and _is_tab_path(path)
                and not any(key in item for key in ("tabIndex", "tab_index", "index"))
            ):
                child = {**item, "index": index}
            _extract_structure(
                child,
                tabs=tabs,
                sections=sections,
                widgets=widgets,
                source=source,
                tab_context=tab_context,
                section_context=section_context,
                path=path,
            )
        return
    if not isinstance(value, dict):
        return

    parsed_tabs = _parse_jsonish(value.get("tabs"))
    if isinstance(parsed_tabs, list):
        _extract_structure(
            parsed_tabs,
            tabs=tabs,
            sections=sections,
            widgets=widgets,
            source=source,
            tab_context=tab_context,
            section_context=section_context,
            path=(*path, "tabs"),
        )

    current_tab = _tab_from_candidate(value, path) or tab_context
    if current_tab is not None:
        tabs.append(current_tab)
    current_section = _section_from_candidate(value, current_tab) or section_context
    if current_section is not None:
        sections.append(current_section)

    layout_cards = _ordered_layout_cards(value)
    if layout_cards:
        active_section = current_section
        section_count = 0
        for widget_order, (layout_key, layout_card) in enumerate(layout_cards):
            text_section = _section_from_text_card(
                layout_card,
                current_tab,
                section_index=section_count,
            )
            if text_section is not None:
                sections.append(text_section)
                active_section = text_section
                section_count += 1
                continue
            widget = _widget_from_candidate(
                layout_card,
                source,
                current_tab,
                active_section,
                fallback_widget_id=layout_key,
                widget_order=widget_order,
            )
            if widget is not None:
                widgets.append(widget)
        return

    widget = _widget_from_candidate(value, source, current_tab, current_section)
    if widget is not None:
        widgets.append(widget)

    for key, child in value.items():
        if key == "tabs" and isinstance(parsed_tabs, list):
            continue
        _extract_structure(
            child,
            tabs=tabs,
            sections=sections,
            widgets=widgets,
            source=source,
            tab_context=current_tab,
            section_context=current_section,
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


def _section_from_candidate(
    item: dict[str, Any],
    tab_context: QuantumDashboardTab | None,
) -> QuantumDashboardSection | None:
    raw_section = item.get("section") or item.get("group") or item.get("container")
    section = raw_section if isinstance(raw_section, dict) else {}
    section_id = _text(
        item.get("sectionId")
        or item.get("section_id")
        or section.get("id")
        or section.get("sectionId")
    )
    section_name = _text(
        item.get("sectionName")
        or item.get("section_name")
        or section.get("name")
        or section.get("title")
    )
    if not section_id and not section_name:
        return None
    tab_index = _int(
        item.get("tabIndex") or item.get("tab_index") or section.get("tabIndex"),
        tab_context.tab_index if tab_context is not None else 0,
    )
    return QuantumDashboardSection(
        section_id=section_id,
        tab_id=_text(
            item.get("tabId")
            or item.get("tab_id")
            or section.get("tabId")
            or (tab_context.tab_id if tab_context is not None else None)
        ),
        tab_index=tab_index,
        name=section_name or "Sin sección",
        section_index=_int(
            item.get("sectionIndex") or item.get("section_index") or section.get("index"),
            0,
        ),
    )


def _widget_from_candidate(
    item: dict[str, Any],
    source: StructureSource,
    tab_context: QuantumDashboardTab | None,
    section_context: QuantumDashboardSection | None,
    *,
    fallback_widget_id: str | None = None,
    widget_order: int | None = None,
) -> QuantumDashboardWidget | None:
    if any(key in item for key in ("tabs", "cards")) and not any(
        key in item for key in ("adHocData", "card", "cardId", "card_id", "widgetId", "widget_id")
    ):
        return None
    ad_hoc_raw = item.get("adHocData")
    ad_hoc: dict[str, Any] = ad_hoc_raw if isinstance(ad_hoc_raw, dict) else {}
    card_raw = ad_hoc.get("card")
    card: dict[str, Any] = card_raw if isinstance(card_raw, dict) else {}
    explicit_card_raw = item.get("card")
    explicit_card: dict[str, Any] = explicit_card_raw if isinstance(explicit_card_raw, dict) else {}
    card = {**explicit_card, **card}
    component = _text(item.get("component") or card.get("component"))
    if component and component.casefold() == "text" and not card:
        return None
    card_id = _text(
        item.get("cardId")
        or item.get("card_id")
        or item.get("cardUuid")
        or card.get("id")
        or card.get("cardId")
    )
    widget_id = _text(
        item.get("widgetId")
        or item.get("widget_id")
        or item.get("id")
        or fallback_widget_id
        or card_id
        or card.get("id")
    )
    title = _text(
        item.get("cardTitle")
        or item.get("title")
        or item.get("name")
        or card.get("title")
        or card.get("name")
    )
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
    resolved_widget_order = _int_or_none(
        item.get("widgetOrder")
        or item.get("widget_order")
        or item.get("order")
        or item.get("index")
    )
    if resolved_widget_order is None:
        resolved_widget_order = widget_order
    visualization = _text(
        card.get("visualization")
        or card.get("visualizationType")
        or item.get("visualization")
        or item.get("visualizationType")
        or item.get("visualization_type")
    )
    raw_type = _text(
        visualization
        or item.get("cardType")
        or item.get("card_type")
        or item.get("widgetType")
        or item.get("widget_type")
        or item.get("type")
        or card.get("type")
        or component
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
    widget_type = _to_config_widget_type(kind)
    if role is None and is_supported_generic_widget_type(widget_type):
        role = generic_role_for_widget(
            widget_id=widget_id,
            card_id=card_id,
            widget_type=widget_type,
            tab_index=tab_index,
        )
    support = assess_widget_support(
        widget_id=widget_id,
        title=title,
        widget_type=widget_type,
        visual_role=role,
    )
    return QuantumDashboardWidget(
        widget_id=widget_id,
        card_id=card_id,
        title=title,
        tab_id=tab_context.tab_id if tab_context is not None else None,
        tab_name=tab_name,
        tab_index=tab_index,
        section_id=_text(item.get("sectionId") or item.get("section_id"))
        or (section_context.section_id if section_context is not None else None),
        section_name=_text(item.get("sectionName") or item.get("section_name"))
        or (section_context.name if section_context is not None else None),
        section_index=_int_or_none(item.get("sectionIndex") or item.get("section_index"))
        if item.get("sectionIndex") is not None or item.get("section_index") is not None
        else (section_context.section_index if section_context is not None else None),
        widget_order=resolved_widget_order,
        layout_x=_int_or_none(item.get("layout_x") if "layout_x" in item else item.get("x")),
        layout_y=_int_or_none(item.get("layout_y") if "layout_y" in item else item.get("y")),
        layout_width=_int_or_none(
            item.get("layout_width")
            if "layout_width" in item
            else item.get("w") or item.get("width")
        ),
        layout_height=_int_or_none(
            item.get("layout_height")
            if "layout_height" in item
            else item.get("h") or item.get("height")
        ),
        visual_contract=_visual_contract_from_candidate(item, card, visualization),
        visual_role=role,
        widget_type=kind,
        enabled=bool(role),
        required=support.supported,
        supported=support.supported,
        source=source,
    )


def _dedupe_tabs(tabs: list[QuantumDashboardTab]) -> list[QuantumDashboardTab]:
    by_key: dict[tuple[int, str], QuantumDashboardTab] = {}
    for tab in tabs:
        by_key.setdefault((tab.tab_index, tab.name), tab)
    return sorted(by_key.values(), key=lambda tab: (tab.tab_index, tab.name.casefold()))


def _dedupe_sections(
    sections: list[QuantumDashboardSection],
) -> list[QuantumDashboardSection]:
    by_key: dict[tuple[int, int, str], QuantumDashboardSection] = {}
    for section in sections:
        key = (section.tab_index, section.section_index, section.section_id or section.name)
        by_key.setdefault(key, section)
    return [by_key[key] for key in sorted(by_key)]


def _dedupe_widgets(widgets: list[QuantumDashboardWidget]) -> list[QuantumDashboardWidget]:
    by_key: dict[str, QuantumDashboardWidget] = {}
    for widget in widgets:
        by_key.setdefault(widget.widget_id, widget)
    return sorted(
        by_key.values(),
        key=lambda widget: (
            widget.tab_index,
            widget.widget_order if widget.widget_order is not None else 999_999,
            widget.title.casefold(),
        ),
    )


def _dashboard_name_from_payload(value: Any) -> str | None:
    if isinstance(value, list):
        for item in value:
            name = _dashboard_name_from_payload(item)
            if name:
                return name
        return None
    if not isinstance(value, dict):
        return None
    entity = value.get("entity")
    if isinstance(entity, dict):
        name = _text(entity.get("title") or entity.get("name"))
        if name:
            return name
    data = value.get("data")
    if isinstance(data, dict):
        name = _dashboard_name_from_payload(data)
        if name:
            return name
    resource = value.get("resource")
    if isinstance(resource, dict):
        name = _dashboard_name_from_payload(resource)
        if name:
            return name
    return _text(value.get("dashboardName") or value.get("name") or value.get("title"))


def _ordered_layout_cards(item: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    layout_cards = item.get("layoutCardsMap")
    if not isinstance(layout_cards, dict):
        return []
    positions = _layout_position_map(item.get("layout"))
    rows: list[tuple[tuple[int, int, int], str, dict[str, Any]]] = []
    for index, (key, value) in enumerate(layout_cards.items()):
        if not isinstance(value, dict):
            continue
        layout = positions.get(str(key))
        sort_key = (
            (layout[1], layout[0], index)
            if layout
            else (
                _int(value.get("y"), index),
                _int(value.get("x"), 0),
                index,
            )
        )
        enriched = (
            {
                **value,
                "layout_x": layout[0],
                "layout_y": layout[1],
                "layout_width": layout[2],
                "layout_height": layout[3],
            }
            if layout
            else value
        )
        rows.append((sort_key, str(key), enriched))
    return [(key, value) for _, key, value in sorted(rows, key=lambda row: row[0])]


def _layout_position_map(layout: Any) -> dict[str, tuple[int, int, int, int]]:
    if isinstance(layout, dict):
        candidates = list(layout.values())
    elif isinstance(layout, list):
        candidates = layout
    else:
        return {}
    positions: dict[str, tuple[int, int, int, int]] = {}
    for index, item in enumerate(candidates):
        if not isinstance(item, dict):
            continue
        key = _text(item.get("i") or item.get("id") or item.get("cardId") or item.get("card_id"))
        if not key:
            continue
        positions[key] = (
            _int(item.get("x"), 0),
            _int(item.get("y"), index),
            max(1, _int(item.get("w") or item.get("width"), 1)),
            max(1, _int(item.get("h") or item.get("height"), 1)),
        )
    return positions


def _visual_contract_from_candidate(
    item: dict[str, Any],
    card: dict[str, Any],
    visualization: str | None,
) -> dict[str, Any]:
    explicit = (
        item.get("widgetContract")
        or item.get("widget_contract")
        or item.get("visualContract")
        or item.get("visual_contract")
        or card.get("contract")
    )
    contract: dict[str, Any] = {}
    value = (
        item.get("valueContract")
        or item.get("displayNumber")
        or card.get("valueContract")
        or card.get("displayNumber")
    )
    if isinstance(value, dict):
        contract["value"] = value
    comparison = item.get("comparison") or card.get("comparison")
    if isinstance(comparison, dict):
        contract["comparison"] = comparison
    chart = item.get("chartContract") or card.get("chartContract") or card.get("chart")
    if isinstance(chart, dict):
        contract["chart"] = chart
    elif visualization:
        contract["visualization_type"] = visualization
    table = item.get("tableContract") or card.get("tableContract")
    if isinstance(table, dict):
        contract["table"] = table
    elif isinstance(card.get("columns"), list):
        contract["table"] = {"columns": card["columns"]}
    contract.update(_display_settings_from_card(card))
    query = _query_contract_from_card(card)
    if query:
        contract["query"] = query
    if isinstance(explicit, dict):
        contract = _merge_contracts(contract, explicit)
    return contract


def _section_from_text_card(
    item: dict[str, Any],
    tab: QuantumDashboardTab | None,
    *,
    section_index: int,
) -> QuantumDashboardSection | None:
    if str(item.get("component") or "").strip().casefold() != "text":
        return None
    name = _text(item.get("textValue") or item.get("text") or item.get("content"))
    if not name or tab is None:
        return None
    return QuantumDashboardSection(
        section_id=_text(item.get("id") or item.get("sectionId")),
        tab_id=tab.tab_id,
        tab_index=tab.tab_index,
        name=name,
        section_index=section_index,
    )


def _display_settings_from_card(card: dict[str, Any]) -> dict[str, Any]:
    entities = card.get("entities")
    metric_entities = entities.get("metricEntities") if isinstance(entities, dict) else None
    if not isinstance(metric_entities, list) or not metric_entities:
        return {}
    first_metric = next((item for item in metric_entities if isinstance(item, dict)), None)
    if first_metric is None:
        return {}
    diff = first_metric.get("diff")
    if not isinstance(diff, dict):
        return {}
    kpi_value = diff.get("kpi")
    kpi: dict[str, Any] = kpi_value if isinstance(kpi_value, dict) else {}
    raw_format = kpi.get("format") or diff.get("format")
    tokens = _format_tokens(raw_format)
    unit = "percent" if "percent" in tokens or diff.get("showPercent") is True else "count"
    precision = _precision_from_tokens(tokens)
    settings: dict[str, Any] = {
        "unit": unit,
        "scale": 100 if unit == "percent" else 1,
        "formatter": ":".join(tokens) if tokens else None,
    }
    if precision is not None:
        settings["precision"] = precision
    if unit == "percent":
        settings["suffix"] = "%"
    increases_are = _text(diff.get("increasesAre"))
    historical_type = _text(diff.get("historicalType"))
    if increases_are:
        settings["increases_are"] = increases_are
    if historical_type:
        settings["historical_type"] = historical_type
    return {key: value for key, value in settings.items() if value is not None}


def _query_contract_from_card(card: dict[str, Any]) -> dict[str, Any]:
    entities = card.get("entities")
    metric_entities = entities.get("metricEntities") if isinstance(entities, dict) else None
    metric_ids = sorted(
        {
            str(item.get("id"))
            for item in metric_entities or []
            if isinstance(item, dict) and item.get("id")
        }
    )
    dimensions_value = card.get("dimensions")
    dimensions = dimensions_value.get("dimensions") if isinstance(dimensions_value, dict) else None
    query_dimensions: list[dict[str, Any]] = []
    selections: set[str] = set()
    for item in dimensions or []:
        if not isinstance(item, dict):
            continue
        metadata_value = item.get("metadata")
        metadata: dict[str, Any] = metadata_value if isinstance(metadata_value, dict) else {}
        values = sorted(
            {
                str(value)
                for value in item.get("selections") or []
                if value is not None and str(value).strip()
            }
        )
        selections.update(values)
        query_dimensions.append(
            {
                "column": _text(item.get("column") or metadata.get("column")),
                "label": _text(item.get("name") or metadata.get("name")),
                "selections": values,
            }
        )
    if not metric_ids and not query_dimensions:
        return {}
    fingerprint_payload = {
        "metric_ids": metric_ids,
        "dimensions": query_dimensions,
    }
    return {
        **fingerprint_payload,
        "selection_tokens": sorted(selections),
        "fingerprint": hashlib.sha256(
            json.dumps(
                fingerprint_payload,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
    }


def _format_tokens(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else [value]
    return [str(item).strip().casefold() for item in raw if item is not None and str(item).strip()]


def _precision_from_tokens(tokens: list[str]) -> int | None:
    mapping = {
        "integer": 0,
        "comma": 0,
        "ones": 0,
        "tenths": 1,
        "hundredths": 2,
        "thousandths": 3,
    }
    return next((mapping[token] for token in reversed(tokens) if token in mapping), None)


def _merge_contracts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _merge_contracts(current, value)
        else:
            merged[key] = value
    return merged


def _parse_jsonish(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text[0] not in "[{":
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _capture_query_headers(
    request: Any,
    query_headers_ref: dict[str, dict[str, str] | None],
) -> None:
    if query_headers_ref.get("value") is not None:
        return
    headers = _query_headers_from_request(request)
    if headers:
        query_headers_ref["value"] = headers


def _query_headers_from_request(request: Any) -> dict[str, str] | None:
    try:
        if str(request.method).upper() != "POST" or not _is_quantum_graphql_url(request.url):
            return None
        headers = {str(key).lower(): str(value) for key, value in request.headers.items()}
        if not headers.get("authorization"):
            return None
        safe_headers = {
            key: value
            for key, value in headers.items()
            if key in {"authorization", "content-type", "referer", "user-agent"}
            or key.startswith("x-")
        }
        safe_headers.setdefault("content-type", "application/json")
        return safe_headers
    except Exception:
        return None


def _collect_load_dashboard_payload(
    response: Any,
    payloads: list[Any],
    dashboard_id: str,
) -> None:
    try:
        content_type = str(response.headers.get("content-type") or "")
        if "json" not in content_type.casefold() or not _is_quantum_graphql_url(response.url):
            return
        request_body = _parse_request_json(response.request)
        if not _is_load_dashboard_request(request_body, dashboard_id):
            return
        body = response.body()
        if len(body) > 8_000_000:
            return
        payload = json.loads(body.decode("utf-8", "replace"))
    except Exception:
        return
    if _payload_matches_dashboard(payload, dashboard_id):
        payloads.append(payload)


def _is_load_dashboard_request(payload: dict[str, Any], dashboard_id: str) -> bool:
    operation_name = _text(payload.get("operationName"))
    query = _text(payload.get("query")) or ""
    variables = payload.get("variables")
    payload_dashboard_id = _text(
        variables.get("dashboardId") if isinstance(variables, dict) else None
    )
    return (
        operation_name == "LoadDashboard"
        or "LoadDashboard" in query
        or payload_dashboard_id == dashboard_id
    )


def _payload_matches_dashboard(payload: Any, dashboard_id: str) -> bool:
    if not isinstance(payload, dict):
        return False
    data = payload.get("data")
    resource = data.get("resource") if isinstance(data, dict) else None
    if not isinstance(resource, dict):
        return False
    entity = resource.get("entity")
    return _text(
        resource.get("id") or (entity.get("id") if isinstance(entity, dict) else None)
    ) in {
        dashboard_id,
        None,
    }


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
    hostname = parsed.hostname or ""
    is_allowed_host = hostname == "quantummetric.com" or hostname.endswith(".quantummetric.com")
    return is_allowed_host and parsed.path.rstrip("/") == "/query"


def _wait_for_structure_payload(page: Any, payloads: list[Any], wait_seconds: int) -> None:
    started = time.monotonic()
    deadline = started + max(5, min(wait_seconds, 45))
    while time.monotonic() < deadline:
        page.wait_for_timeout(500)
        if payloads and time.monotonic() - started >= 1:
            return


def _load_dashboard_payload(dashboard_id: str) -> dict[str, Any]:
    return {
        "operationName": "LoadDashboard",
        "query": LOAD_DASHBOARD_QUERY,
        "variables": {"dashboardId": dashboard_id},
    }


def _dashboard_url(base_url: str, dashboard_id: str, team_id: str | None) -> str:
    parsed = urlparse(base_url)
    origin = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
    query = urlencode({"teamID": team_id}) if team_id else ""
    suffix = f"?{query}" if query else ""
    return f"{origin.rstrip()}/#/dashboard/{dashboard_id}{suffix}"


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


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
