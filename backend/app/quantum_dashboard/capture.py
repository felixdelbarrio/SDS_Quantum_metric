from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.app.auth.browser_cookies import BrowserCookie
from backend.app.config.settings import Settings
from backend.app.ingestion.capture import QuantumAnalyticsCaptureSession, capture_quantum_analytics
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
    session_mode: str = "manual",
    capture_session: QuantumAnalyticsCaptureSession | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    if capture_session is None:
        with QuantumAnalyticsCaptureSession(
            settings=settings,
            cookies=cookies,
            country=country,
            base_url=base_url,
            wait_seconds=settings.quantum_capture_timeout_seconds,
            ingestion_id=ingestion_id,
            session_mode=session_mode,
        ) as session:
            return capture_quantum_dashboard_cards(
                settings=settings,
                cookies=cookies,
                country=country,
                base_url=base_url,
                dashboard_id=dashboard_id,
                team_id=team_id,
                summary_tab=summary_tab,
                errors_tab=errors_tab,
                ingestion_id=ingestion_id,
                ingestion_range=ingestion_range,
                capture_session=session,
                session_mode=session_mode,
                progress_callback=progress_callback,
            )

    rows: list[dict[str, Any]] = []
    for tab_name, tab_index in (("summary", summary_tab), ("errors", errors_tab)):
        if progress_callback is not None:
            progress_callback(tab_name)
        dashboard_url = dashboard_tab_url(
            base_url=base_url,
            dashboard_id=dashboard_id,
            team_id=team_id,
            tab=tab_index,
        )
        if capture_session:
            captured = capture_session.capture(
                dashboard_url=dashboard_url,
                ingestion_range=ingestion_range,
            )
        else:
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
        if not captured:
            tab_label = "Resumen" if tab_name == "summary" else "Errores"
            raise RuntimeError(
                "No Quantum analytics responses were captured for "
                f"{tab_label}. Check that the local controlled session is authenticated "
                "and that the dashboard emits /analytics responses for the selected range."
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
