from __future__ import annotations

from backend.app.ingestion.service import _filter_enabled_rows


def test_filter_enabled_rows_excludes_disabled_widget_calls() -> None:
    rows = [
        {
            "card_id": "page-views",
            "card_title": "Paginas vistas",
            "card_type": "CHART",
            "view_name": "coreMetrics",
        },
        {
            "card_id": "sessions",
            "card_title": "Sesiones",
            "card_type": "CHART",
            "view_name": "coreMetrics",
        },
    ]

    filtered = _filter_enabled_rows(rows, {"summary.sessions"})

    assert [row["card_id"] for row in filtered] == ["sessions"]
