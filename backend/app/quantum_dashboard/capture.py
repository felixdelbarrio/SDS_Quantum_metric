from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.app.auth.browser_cookies import BrowserCookie
from backend.app.config.settings import Settings
from backend.app.ingestion.capture import (
    QuantumAnalyticsCaptureSession,
    QuantumAuthenticationRequired,
    capture_quantum_analytics,
)
from backend.app.ingestion.policy import IngestionRange
from backend.app.quantum.schemas import QuantumWidgetConfig
from backend.app.quantum_dashboard.discovery import dashboard_tab_url
from backend.app.quantum_dashboard.widget_roles import (
    descriptors_from_widgets,
    enrich_calls_with_live_contracts,
)

type DashboardCaptureTab = dict[str, int | str | None]


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
    tabs: list[DashboardCaptureTab] | None = None,
    widgets: list[QuantumWidgetConfig] | None = None,
    ingestion_id: str,
    ingestion_range: IngestionRange | None,
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
                tabs=tabs,
                widgets=widgets,
                ingestion_id=ingestion_id,
                ingestion_range=ingestion_range,
                capture_session=session,
                progress_callback=progress_callback,
            )

    rows: list[dict[str, Any]] = []
    tab_failures: list[str] = []
    configured_tabs = _capture_tabs(tabs, summary_tab, errors_tab)
    for tab in configured_tabs:
        tab_name = str(tab["tab"])
        tab_index = int(str(tab["tab_index"] or 0))
        tab_label = str(tab["tab_name"])
        if progress_callback is not None:
            progress_callback(tab_label)
        dashboard_url = dashboard_tab_url(
            base_url=base_url,
            dashboard_id=dashboard_id,
            team_id=team_id,
            tab=tab_index,
            range_key=ingestion_range.range_key if ingestion_range else None,
        )
        try:
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
        except QuantumAuthenticationRequired:
            raise
        except RuntimeError as exc:
            captured = []
            tab_failures.append(f"{tab_label}: {exc}")
        if not captured:
            tab_failures.append(f"{tab_label}: sin respuestas analytics")
            continue
        for row in captured:
            row["tab"] = tab_name
            row["tab_name"] = tab_label
            row["tab_index"] = tab_index
            row["endpoint"] = row.get("source_endpoint")
            row["method"] = row.get("http_method")
            row["captured_at"] = row.get("ingestion_ts")
            row.setdefault("parse_status", "pending")
            row.setdefault("parse_error", None)
        captured = enrich_calls_with_live_contracts(
            captured,
            descriptors=descriptors_from_widgets(widgets),
            live_contracts=getattr(capture_session, "last_visual_contracts", {}),
        )
        rows.extend(captured)
    if not rows:
        details = " | ".join(dict.fromkeys(tab_failures))
        raise RuntimeError(
            f"No Quantum analytics responses were captured for any configured tab. {details}"
        )
    return rows


def _capture_tabs(
    tabs: list[DashboardCaptureTab] | None,
    summary_tab: int,
    errors_tab: int,
) -> list[DashboardCaptureTab]:
    if tabs:
        normalized: list[DashboardCaptureTab] = []
        seen: set[int] = set()
        for tab in tabs:
            raw_index = tab.get("tab_index")
            if raw_index is None:
                raw_index = tab.get("tab")
            try:
                tab_index = int(raw_index or 0)
            except (TypeError, ValueError):
                tab_index = 0
            if tab_index in seen:
                continue
            seen.add(tab_index)
            tab_name = str(tab.get("tab_name") or tab.get("name") or f"Tab {tab_index + 1}")
            tab_token = str(tab.get("tab") or _slug(tab_name) or f"tab-{tab_index}")
            normalized.append({"tab": tab_token, "tab_name": tab_name, "tab_index": tab_index})
        if normalized:
            return sorted(normalized, key=lambda item: int(item["tab_index"] or 0))
    return [
        {"tab": "summary", "tab_name": "Resumen", "tab_index": summary_tab},
        {"tab": "errors", "tab_name": "Errores", "tab_index": errors_tab},
    ]


def _slug(value: str) -> str:
    return value.strip().casefold().replace("_", " ")
