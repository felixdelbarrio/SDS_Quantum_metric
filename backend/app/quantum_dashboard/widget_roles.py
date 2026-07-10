from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.analytics.normalizer import parse_json_object
from backend.app.quantum.schemas import QuantumDashboardConfig, QuantumWidgetConfig
from backend.app.quantum_dashboard.card_mapper import map_card_role
from backend.app.quantum_dashboard.visual_contracts import merge_visual_contracts


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
        captured_contract = parse_json_object(enriched.get("visual_contract"))
        enriched["visual_contract"] = merge_visual_contracts(
            descriptor.visual_contract,
            captured_contract,
        )
    return enriched


def enrich_calls_with_live_contracts(
    calls: list[dict[str, Any]],
    *,
    descriptors: list[WidgetRoleDescriptor],
    live_contracts: dict[str, dict[str, Any]],
    enabled_roles: set[str] | None = None,
) -> list[dict[str, Any]]:
    completed_live_contracts = _complete_empty_table_contracts(
        descriptors,
        live_contracts,
    )
    enriched_calls: list[dict[str, Any]] = []
    for call in calls:
        role, descriptor = resolve_call_role(
            call,
            descriptors=descriptors,
            enabled_roles=enabled_roles,
        )
        if descriptor is None:
            enriched_calls.append(call)
            continue
        live_contract = completed_live_contracts.get(descriptor.widget_id or "", {})
        merged_call = {
            **call,
            "visual_contract": merge_visual_contracts(
                descriptor.visual_contract,
                live_contract,
            ),
        }
        enriched_calls.append(enrich_call_with_descriptor(merged_call, descriptor, role))
    return enriched_calls


def _complete_empty_table_contracts(
    descriptors: list[WidgetRoleDescriptor],
    live_contracts: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    completed = dict(live_contracts)
    table_schema_by_metrics: dict[tuple[str, ...], dict[str, Any]] = {}
    for descriptor in descriptors:
        live = live_contracts.get(descriptor.widget_id or "", {})
        table = live.get("table")
        signature = _metric_signature(descriptor)
        if signature and isinstance(table, dict) and table.get("columns"):
            table_schema_by_metrics.setdefault(signature, table)
    for descriptor in descriptors:
        widget_id = descriptor.widget_id or ""
        live = completed.get(widget_id, {})
        if descriptor.widget_type != "TABLE" or isinstance(live.get("table"), dict):
            continue
        donor = table_schema_by_metrics.get(_metric_signature(descriptor))
        if donor is None:
            continue
        completed[widget_id] = merge_visual_contracts(
            live,
            {
                "visualization_type": "table",
                "table": {
                    **donor,
                    "rows": [],
                },
            },
        )
    return completed


def _metric_signature(descriptor: WidgetRoleDescriptor) -> tuple[str, ...]:
    query = descriptor.visual_contract.get("query")
    if not isinstance(query, dict):
        return ()
    return tuple(sorted(str(value) for value in query.get("metric_ids") or [] if value))


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
    active = [
        descriptor
        for descriptor in descriptors
        if descriptor.enabled
        and descriptor.supported
        and (enabled_roles is None or descriptor.role in enabled_roles)
    ]
    tab_index = _int_or_none(call.get("tab_index"))
    if tab_index is not None:
        tab_descriptors = [descriptor for descriptor in active if descriptor.tab_index == tab_index]
        if tab_descriptors:
            active = tab_descriptors
    widget_id = _text(call.get("widget_id"))
    card_id = _text(call.get("card_id"))
    for value, attribute in ((widget_id, "widget_id"), (card_id, "card_id")):
        if not value:
            continue
        candidates = [
            descriptor for descriptor in active if getattr(descriptor, attribute) == value
        ]
        if len(candidates) == 1:
            return candidates[0]
        matched = [
            descriptor for descriptor in candidates if descriptor_query_matches(call, descriptor)
        ]
        if len(matched) == 1:
            return matched[0]
    matched = [descriptor for descriptor in active if descriptor_query_matches(call, descriptor)]
    if len(matched) == 1:
        return matched[0]
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


def descriptor_query_matches(
    call: dict[str, Any],
    descriptor: WidgetRoleDescriptor,
) -> bool:
    query = descriptor.visual_contract.get("query")
    if not isinstance(query, dict):
        return False
    selection_tokens = {
        str(value)
        for value in query.get("selection_tokens") or []
        if value is not None and str(value).strip()
    }
    metric_ids = {
        str(value)
        for value in query.get("metric_ids") or []
        if value is not None and str(value).strip()
    }
    if not selection_tokens and not metric_ids:
        return False
    request = parse_json_object(call.get("request_json"))
    request_tokens = _scalar_tokens(request)
    if selection_tokens and not selection_tokens.issubset(request_tokens):
        return False
    if metric_ids and not metric_ids.issubset(request_tokens):
        return False
    return bool(selection_tokens or metric_ids)


def _scalar_tokens(value: Any) -> set[str]:
    if isinstance(value, dict):
        return {token for item in value.values() for token in _scalar_tokens(item)}
    if isinstance(value, list):
        return {token for item in value for token in _scalar_tokens(item)}
    if isinstance(value, str) and value.strip():
        return {value.strip()}
    return set()


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
