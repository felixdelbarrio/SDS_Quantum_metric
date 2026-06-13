from __future__ import annotations

from backend.app.analytics.models import DashboardDimension, DashboardDimensionGroup
from backend.app.analytics.normalizer import humanize_key

DIMENSION_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Page", ("application_type", "application_version", "app_name")),
    ("Device", ("ai_detected", "browser", "operating_system", "platform", "device_type")),
    ("Custom Events", ("active_fix", "active_test")),
)


def build_dimension_groups(
    discovered_dimensions: dict[str, str],
) -> list[DashboardDimensionGroup]:
    consumed: set[str] = set()
    groups: list[DashboardDimensionGroup] = []

    for group_label, keys in DIMENSION_GROUPS:
        items: list[DashboardDimension] = []
        for key in keys:
            if key in discovered_dimensions:
                items.append(
                    DashboardDimension(
                        id=key,
                        label=discovered_dimensions.get(key) or humanize_key(key),
                    )
                )
                consumed.add(key)
        if items:
            groups.append(DashboardDimensionGroup(label=group_label, items=items))

    other_items = [
        DashboardDimension(id=key, label=label or humanize_key(key))
        for key, label in sorted(discovered_dimensions.items())
        if key not in consumed
    ]
    if other_items:
        groups.append(DashboardDimensionGroup(label="Other", items=other_items))

    return groups
