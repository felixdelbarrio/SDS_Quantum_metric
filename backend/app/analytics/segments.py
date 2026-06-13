from __future__ import annotations

from collections import Counter

from backend.app.analytics.models import DashboardSegment
from backend.app.analytics.normalizer import NormalizedRecord, humanize_key

SEGMENT_FIELDS = (
    "platform",
    "app_name",
    "browser",
    "application_type",
    "operating_system",
)


def build_segments(records: list[NormalizedRecord]) -> list[DashboardSegment]:
    counters: dict[str, Counter[str]] = {field: Counter() for field in SEGMENT_FIELDS}
    error_count = 0
    no_error_count = 0
    conversion_count = 0
    no_conversion_count = 0

    for record in records:
        for field in SEGMENT_FIELDS:
            value = record.dimension(field)
            if value:
                counters[field][value] += 1

        error_sessions = record.metric("sessions_with_error")
        if error_sessions is not None and error_sessions > 0:
            error_count += 1
        elif error_sessions is not None:
            no_error_count += 1

        converted = record.metric("converted_sessions")
        if converted is not None and converted > 0:
            conversion_count += 1
        elif converted is not None:
            no_conversion_count += 1

    segments: list[DashboardSegment] = []
    for field, counter in counters.items():
        for value, count in counter.most_common(20):
            segments.append(
                DashboardSegment(
                    id=f"{field}:{value}",
                    label=f"{humanize_key(field)}: {value}",
                    field=field,
                    value=value,
                    count=count,
                )
            )

    if error_count:
        segments.append(
            DashboardSegment(
                id="error_state:with_error",
                label="Error: con error",
                field="error_state",
                value="with_error",
                count=error_count,
            )
        )
    if no_error_count:
        segments.append(
            DashboardSegment(
                id="error_state:without_error",
                label="Error: sin error",
                field="error_state",
                value="without_error",
                count=no_error_count,
            )
        )
    if conversion_count:
        segments.append(
            DashboardSegment(
                id="conversion_state:converted",
                label="Conversion: con conversion",
                field="conversion_state",
                value="converted",
                count=conversion_count,
            )
        )
    if no_conversion_count:
        segments.append(
            DashboardSegment(
                id="conversion_state:not_converted",
                label="Conversion: sin conversion",
                field="conversion_state",
                value="not_converted",
                count=no_conversion_count,
            )
        )

    return segments


def parse_segment(segment_id: str | None) -> tuple[str, str] | None:
    if not segment_id or ":" not in segment_id:
        return None
    field, value = segment_id.split(":", 1)
    if not field or not value:
        return None
    return field, value
