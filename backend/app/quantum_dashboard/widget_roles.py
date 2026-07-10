from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.quantum.schemas import QuantumDashboardConfig, QuantumWidgetConfig
from backend.app.quantum_dashboard.card_mapper import map_card_role


@dataclass(frozen=True)
class WidgetRoleDescriptor:
    role: str
    title: str
    widget_id: str | None
    card_id: str | None
    widget_type: str
    tab: str
    tab_id: str | None
    tab_name: str
    tab_index: int
    section_id: str | None
    section_name: str | None
    section_index: int | None
    widget_order: int | None
    layout_x: int | None
    layout_y: int | None
    layout_width: int | None
    layout_height: int | None
    visual_contract: dict[str, Any]
    enabled: bool
    supported: bool
    required: bool


def descriptors_from_dashboard(
    dashboard: QuantumDashboardConfig | None,
) -> list[WidgetRoleDescriptor]:
    if dashboard is None:
        return []
    return descriptors_from_widgets(dashboard.widgets)


def descriptors_from_widgets(
    widgets: list[QuantumWidgetConfig] | None,
) -> list[WidgetRoleDescriptor]:
    descriptors: list[WidgetRoleDescriptor] = []
    for widget in widgets or []:
        if not widget.role:
            continue
        descriptors.append(_descriptor(widget))
    return descriptors


def enabled_descriptors_from_dashboard(
    dashboard: QuantumDashboardConfig | None,
) -> list[WidgetRoleDescriptor]:
    return [
        descriptor
        for descriptor in descriptors_from_dashboard(dashboard)
        if descriptor.enabled and descriptor.supported
    ]


def resolve_call_role(
    call: dict[str, Any],
    *,
    descriptors: list[WidgetRoleDescriptor] | None = None,
    enabled_roles: set[str] | None = None,
) -> tuple[str | None, WidgetRoleDescriptor | None]:
    descriptor = _descriptor_for_call(call, descriptors or [], enabled_roles)
    if descriptor is not None:
        return descriptor.role, descriptor
    if _has_ambiguous_strong_match(call, descriptors or [], enabled_roles):
        return None, None
    mapped = map_card_role(call)
    if mapped is None:
        return None, None
    role = str(mapped)
    if enabled_roles is not None and role not in enabled_roles:
        return None, None
    return role, None


def enrich_call_with_descriptor(
    call: dict[str, Any],
    descriptor: WidgetRoleDescriptor | None,
    role: str | None,
) -> dict[str, Any]:
    if descriptor is None and role is None:
        return call
    enriched = dict(call)
    if role:
        enriched["card_role"] = role
        enriched["visual_role"] = role
    if descriptor is not None:
        enriched["card_title"] = enriched.get("card_title") or descriptor.title
        enriched["widget_id"] = enriched.get("widget_id") or descriptor.widget_id
        enriched["card_id"] = enriched.get("card_id") or descriptor.card_id
        enriched["card_type"] = enriched.get("card_type") or descriptor.widget_type
        enriched["widget_type"] = enriched.get("widget_type") or descriptor.widget_type
        enriched["tab"] = descriptor.tab
        enriched["tab_id"] = descriptor.tab_id
        enriched["tab_name"] = descriptor.tab_name
        enriched["tab_index"] = descriptor.tab_index
        enriched["section_id"] = descriptor.section_id
        enriched["section_name"] = descriptor.section_name
        enriched["section_index"] = descriptor.section_index
        enriched["widget_order"] = descriptor.widget_order
        enriched["layout_x"] = descriptor.layout_x
        enriched["layout_y"] = descriptor.layout_y
        enriched["layout_width"] = descriptor.layout_width
        enriched["layout_height"] = descriptor.layout_height
        enriched["visual_contract"] = descriptor.visual_contract
    return enriched


def enrich_ambiguous_calls_with_descriptor_sequence(
    calls: list[dict[str, Any]],
    *,
    descriptors: list[WidgetRoleDescriptor] | None = None,
    enabled_roles: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Enrich only calls with a unique strong identifier match.

    Iteration 18 deliberately removed the former TABLE round-robin fallback. A
    repeated card id is ambiguous and must be handled as a correlation error.
    """
    resolved_descriptors = descriptors or []
    if not resolved_descriptors:
        return calls
    enriched_calls: list[dict[str, Any]] = []
    for call in calls:
        role, descriptor = resolve_call_role(
            call,
            descriptors=resolved_descriptors,
            enabled_roles=enabled_roles,
        )
        if descriptor is not None:
            enriched_calls.append(enrich_call_with_descriptor(call, descriptor, role))
            continue
        enriched_calls.append(call)
    return enriched_calls


def role_tab_from_descriptors(role: str, descriptors: list[WidgetRoleDescriptor]) -> str | None:
    descriptor = next((item for item in descriptors if item.role == role), None)
    return descriptor.tab if descriptor is not None else None


def _descriptor(widget: QuantumWidgetConfig) -> WidgetRoleDescriptor:
    tab = _descriptor_tab(widget)
    return WidgetRoleDescriptor(
        role=widget.role,
        title=widget.title or widget.role,
        widget_id=widget.widget_id or None,
        card_id=widget.card_id or None,
        widget_type=widget.widget_type,
        tab=tab,
        tab_id=widget.tab_id,
        tab_name=widget.tab_name or widget.tab or tab,
        tab_index=widget.tab_index,
        section_id=widget.section_id,
        section_name=widget.section_name,
        section_index=widget.section_index,
        widget_order=widget.widget_order,
        layout_x=widget.layout_x,
        layout_y=widget.layout_y,
        layout_width=widget.layout_width,
        layout_height=widget.layout_height,
        visual_contract=widget.visual_contract,
        enabled=widget.enabled,
        supported=widget.supported,
        required=widget.required,
    )


def _descriptor_tab(widget: QuantumWidgetConfig) -> str:
    tab = _text(widget.tab)
    if tab:
        return tab
    tab_name = _text(widget.tab_name)
    if tab_name:
        return tab_name
    return f"tab-{widget.tab_index}"


def _descriptor_for_call(
    call: dict[str, Any],
    descriptors: list[WidgetRoleDescriptor],
    enabled_roles: set[str] | None,
) -> WidgetRoleDescriptor | None:
    if not descriptors:
        return None
    widget_id = _text(call.get("widget_id"))
    card_id = _text(call.get("card_id"))
    for value, attribute in ((widget_id, "widget_id"), (card_id, "card_id")):
        if not value:
            continue
        candidates = [
            descriptor
            for descriptor in descriptors
            if getattr(descriptor, attribute) == value
            and descriptor.enabled
            and descriptor.supported
            and (enabled_roles is None or descriptor.role in enabled_roles)
        ]
        if len(candidates) == 1:
            return candidates[0]
    return None


def _has_ambiguous_strong_match(
    call: dict[str, Any],
    descriptors: list[WidgetRoleDescriptor],
    enabled_roles: set[str] | None,
) -> bool:
    widget_id = _text(call.get("widget_id"))
    card_id = _text(call.get("card_id"))
    for value, attribute in ((widget_id, "widget_id"), (card_id, "card_id")):
        if not value:
            continue
        candidates = [
            descriptor
            for descriptor in descriptors
            if getattr(descriptor, attribute) == value
            and descriptor.enabled
            and descriptor.supported
            and (enabled_roles is None or descriptor.role in enabled_roles)
        ]
        if len(candidates) > 1:
            return True
    return False


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
