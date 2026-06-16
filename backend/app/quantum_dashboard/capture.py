from __future__ import annotations

from typing import Any

from backend.app.auth.browser_cookies import BrowserCookie
from backend.app.config.settings import Settings
from backend.app.ingestion.capture import capture_quantum_analytics
from backend.app.ingestion.policy import IngestionRange
from backend.app.quantum_dashboard.discovery import dashboard_tab_url


def capture_quantum_dashboard_cards(
    *,
    settings: Settings,
    cookies: list[BrowserCookie],
    country: str,
    base_url: str,
    dashboard_id: str,
    team_id: str | None,
    summary_tab: int,
    errors_tab: int,
    ingestion_id: str,
    ingestion_range: IngestionRange | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tab_name, tab_index in (("summary", summary_tab), ("errors", errors_tab)):
        dashboard_url = dashboard_tab_url(
            base_url=base_url,
            dashboard_id=dashboard_id,
            team_id=team_id,
            tab=tab_index,
        )
        captured = capture_quantum_analytics(
            settings=settings,
            cookies=cookies,
            country=country,
            base_url=base_url,
            dashboard_url=dashboard_url,
            wait_seconds=settings.quantum_capture_timeout_seconds,
            ingestion_id=ingestion_id,
            ingestion_range=ingestion_range,
        )
        for row in captured:
            row["tab"] = tab_name
            row["tab_name"] = "Resumen" if tab_name == "summary" else "Errores"
            row["endpoint"] = row.get("source_endpoint")
            row["method"] = row.get("http_method")
            row["captured_at"] = row.get("ingestion_ts")
            row.setdefault("parse_status", "pending")
            row.setdefault("parse_error", None)
        rows.extend(captured)
    return rows
