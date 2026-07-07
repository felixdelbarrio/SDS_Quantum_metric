from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from backend.app.config.settings import Settings
from backend.app.ingestion.policy import IngestionRange
from backend.app.ingestion.service import _filter_enabled_rows
from backend.app.quantum_dashboard.capture import capture_quantum_dashboard_cards


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


def test_capture_dashboard_cards_keeps_valid_tab_when_other_tab_is_empty(
    tmp_path: Path,
) -> None:
    session = _TabCaptureSession([[], [_raw_row("errors-card")]])

    rows = capture_quantum_dashboard_cards(
        settings=Settings(qm_data_dir=tmp_path),
        cookies=[],
        country="CO",
        base_url="https://bbvaco.quantummetric.com",
        dashboard_id="dash-co",
        team_id="team-co",
        summary_tab=0,
        errors_tab=1,
        ingestion_id="ingestion",
        ingestion_range=IngestionRange(
            "backfill",
            datetime(2026, 7, 1, tzinfo=UTC),
            datetime(2026, 7, 7, tzinfo=UTC),
            None,
            7,
            range_key="last_7_days",
            capture_mode="range_contract",
        ),
        capture_session=cast(Any, session),
    )

    assert [row["card_id"] for row in rows] == ["errors-card"]
    assert rows[0]["tab_name"] == "Errores"
    assert session.urls[-1].endswith("tab=1&teamID=team-co&ts=last_7_days")


def test_capture_dashboard_cards_fails_only_when_all_tabs_are_empty(tmp_path: Path) -> None:
    session = _TabCaptureSession([[], []])

    with pytest.raises(RuntimeError, match="any configured tab"):
        capture_quantum_dashboard_cards(
            settings=Settings(qm_data_dir=tmp_path),
            cookies=[],
            country="CO",
            base_url="https://bbvaco.quantummetric.com",
            dashboard_id="dash-co",
            team_id="team-co",
            summary_tab=0,
            errors_tab=1,
            ingestion_id="ingestion",
            ingestion_range=None,
            capture_session=cast(Any, session),
        )


class _TabCaptureSession:
    def __init__(self, responses: list[list[dict[str, Any]]]) -> None:
        self.responses = responses
        self.urls: list[str] = []

    def capture(
        self,
        *,
        dashboard_url: str,
        ingestion_range: IngestionRange | None,
    ) -> list[dict[str, Any]]:
        _ = ingestion_range
        self.urls.append(dashboard_url)
        return self.responses.pop(0)


def _raw_row(card_id: str) -> dict[str, Any]:
    return {
        "card_id": card_id,
        "source_endpoint": "/analytics",
        "http_method": "POST",
        "ingestion_ts": "2026-07-07T00:00:00Z",
    }
