from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.quantum.schemas import QuantumDashboardConfig, QuantumWidgetConfig
from backend.app.quantum_dashboard.card_mapper import map_card_role
from backend.app.quantum_dashboard.generic_roles import (
    dashboard_tab_for_widget,
    normalized_widget_type,
)


@dataclass(frozen=True)
class WidgetRoleDescriptor:
    role: str
    title: str
    widget_id: str | None
    card_id: str | None
    widget_type: str
    tab: str
    tab_name: str
    tab_index: int
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
        enriched["tab_name"] = descriptor.tab_name
        enriched["tab_index"] = descriptor.tab_index
    return enriched


def enrich_ambiguous_calls_with_descriptor_sequence(
    calls: list[dict[str, Any]],
    *,
    descriptors: list[WidgetRoleDescriptor] | None = None,
    enabled_roles: set[str] | None = None,
) -> list[dict[str, Any]]:
    resolved_descriptors = descriptors or []
    if not resolved_descriptors:
        return calls
    counters: dict[tuple[str, str], int] = {}
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
        descriptor = _sequence_descriptor_for_call(
            call,
            resolved_descriptors,
            counters,
            enabled_roles,
        )
        if descriptor is not None:
            enriched_calls.append(enrich_call_with_descriptor(call, descriptor, descriptor.role))
        else:
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
        tab_name=widget.tab_name or widget.tab or tab,
        tab_index=widget.tab_index,
        enabled=widget.enabled,
        supported=widget.supported,
        required=widget.required,
    )


def _descriptor_tab(widget: QuantumWidgetConfig) -> str:
    if widget.tab_index == 0:
        return "summary"
    if widget.tab_index == 1:
        return "errors"
    return dashboard_tab_for_widget(widget.tab, widget.tab_name, widget.title)


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


def _sequence_descriptor_for_call(
    call: dict[str, Any],
    descriptors: list[WidgetRoleDescriptor],
    counters: dict[tuple[str, str], int],
    enabled_roles: set[str] | None,
) -> WidgetRoleDescriptor | None:
    card_id = _text(call.get("card_id"))
    if not card_id:
        return None
    call_type = normalized_widget_type(call.get("widget_type") or call.get("card_type"))
    candidates = [
        descriptor
        for descriptor in descriptors
        if descriptor.card_id == card_id
        and normalized_widget_type(descriptor.widget_type) == call_type
        and descriptor.enabled
        and descriptor.supported
        and (enabled_roles is None or descriptor.role in enabled_roles)
    ]
    if len(candidates) <= 1:
        return None
    view_name = str(call.get("view_name") or "")
    if call_type != "TABLE" or not view_name:
        return None
    key = (card_id, view_name)
    index = counters.get(key, 0)
    counters[key] = index + 1
    return candidates[index % len(candidates)]


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
