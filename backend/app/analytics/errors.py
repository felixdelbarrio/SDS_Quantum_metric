from __future__ import annotations

from collections import defaultdict

from backend.app.analytics.models import ErrorPercentRow
from backend.app.analytics.normalizer import NormalizedRecord


def calculate_error_rows(
    records: list[NormalizedRecord],
    group_dimension: str = "app_name",
) -> list[ErrorPercentRow]:
    groups: dict[str, dict[str, float]] = defaultdict(
        lambda: {"sessions": 0.0, "sessions_with_error": 0.0, "percent_sum": 0.0, "percent_n": 0.0}
    )

    for record in records:
        name = record.dimension(group_dimension) or record.dimension("app_name") or "Null"
        bucket = groups[name]
        sessions = record.metric("sessions")
        sessions_with_error = record.metric("sessions_with_error")
        percent = record.metric("error_session_percent")

        if sessions is not None:
            bucket["sessions"] += sessions
        if sessions_with_error is not None:
            bucket["sessions_with_error"] += sessions_with_error
        if percent is not None:
            bucket["percent_sum"] += percent
            bucket["percent_n"] += 1

    rows: list[ErrorPercentRow] = []
    for name, values in groups.items():
        sessions = values["sessions"] or None
        sessions_with_error = values["sessions_with_error"] or None
        if sessions and sessions_with_error is not None:
            error_percent = round((sessions_with_error / sessions) * 100, 2)
        elif values["percent_n"]:
            error_percent = round(values["percent_sum"] / values["percent_n"], 2)
        else:
            error_percent = None

        if sessions is None and sessions_with_error is None and error_percent is None:
            continue

        rows.append(
            ErrorPercentRow(
                name=name,
                app_name=name if group_dimension == "app_name" else None,
                sessions=sessions,
                sessions_with_error=sessions_with_error,
                error_session_percent=error_percent,
            )
        )

    return rows
