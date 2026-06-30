from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.app.api import routes
from backend.app.config.settings import Settings
from backend.app.main import app
from backend.app.quantum.schemas import Country, QuantumCountryConfig, QuantumDashboardConfig
from backend.app.quantum_dashboard.builder import DATASET_SUMMARY_WIDGETS, range_dataset_path
from backend.app.quantum_dashboard.dashboard_discovery import (
    dashboards_from_config_cache,
    discover_dashboards_for_country,
    discover_dashboards_from_payloads,
)
from backend.app.quantum_dashboard.dashboard_structure import (
    structure_from_dashboard_config,
    structure_from_payloads,
    widget_configs_from_structure,
)
from backend.app.quantum_dashboard.service import LocalDashboardService
from backend.app.storage.parquet_store import ParquetStore


def test_dashboard_discovery_parses_real_names_types_team_and_dedupes() -> None:
    payload = {
        "data": {
            "dashboards": [
                {
                    "dashboardId": "dash-general-mx",
                    "dashboardName": "Dashboard General MX",
                    "dashboardType": "DASHBOARD",
                    "teamID": "team-mx",
                },
                {
                    "id": "dash-general-mx",
                    "name": "Dashboard General MX",
                    "type": "DASHBOARD",
                    "teamId": "team-mx",
                },
                {
                    "id": "dash-errors",
                    "name": "Errores mobile",
                    "type": "DASHBOARD",
                },
            ]
        }
    }

    dashboards = discover_dashboards_from_payloads(
        [payload],
        country=Country.MX,
        source="quantum_web",
        discovered_at=datetime(2026, 6, 30, tzinfo=UTC),
    )

    assert [dashboard.dashboard_id for dashboard in dashboards] == [
        "dash-general-mx",
        "dash-errors",
    ]
    assert dashboards[0].name == "Dashboard General MX"
    assert dashboards[0].type == "DASHBOARD"
    assert dashboards[0].team_id == "team-mx"
    assert all(dashboard.source == "quantum_web" for dashboard in dashboards)


@pytest.mark.asyncio
async def test_dashboard_discovery_falls_back_to_config_cache() -> None:
    country_config = QuantumCountryConfig(
        country=Country.MX,
        base_url="https://bbvamx.quantummetric.com",
        dashboards=[
            QuantumDashboardConfig(
                dashboard_id="dash-cache",
                name="Dashboard General MX",
                dashboard_type="DASHBOARD",
                is_default=True,
                validated=True,
            )
        ],
    )

    dashboards = await discover_dashboards_for_country(
        Country.MX,
        "https://bbvamx.quantummetric.com",
        _Session(config_cache=country_config),
    )

    cached = dashboards_from_config_cache(country_config)

    assert dashboards[0].dashboard_id == cached[0].dashboard_id
    assert dashboards[0].source == "config_cache"


def test_dashboard_structure_discovers_tabs_widgets_types_and_unknown() -> None:
    payload = {
        "tabs": [
            {
                "tabIndex": 0,
                "name": "Resumen",
                "cards": [
                    {
                        "cardId": "card-page-views",
                        "title": "Paginas vistas",
                        "cardType": "CHART",
                    }
                ],
            },
            {
                "tabIndex": 1,
                "name": "Errores",
                "cards": [
                    {
                        "cardId": "card-app-error",
                        "title": "Comparativa de sesiones con error por App Name",
                        "cardType": "DONUT",
                    },
                    {
                        "cardId": "card-unknown",
                        "title": "Widget sin parser",
                        "cardType": "CHART",
                    },
                ],
            },
        ]
    }

    structure = structure_from_payloads(
        [payload],
        country=Country.MX,
        dashboard_id="dash-general-mx",
        team_id="team-mx",
        source="quantum_web",
    )
    configs = widget_configs_from_structure(structure)

    assert [tab.name for tab in structure.tabs] == ["Resumen", "Errores"]
    assert [(widget.title, widget.widget_type) for widget in structure.widgets] == [
        ("Paginas vistas", "chart"),
        ("Comparativa de sesiones con error por App Name", "donut"),
        ("Widget sin parser", "chart"),
    ]
    assert configs[0].role == "summary.page_views"
    assert configs[1].role == "errors.error_sessions_by_app_name_comparison"
    assert configs[2].role == ""
    assert configs[2].supported is False
    assert configs[2].enabled is False


def test_structure_from_config_cache_keeps_widget_metadata() -> None:
    dashboard = QuantumDashboardConfig(
        dashboard_id="dash",
        name="Dashboard General MX",
        widgets=[],
        is_default=True,
        validated=True,
    )

    structure = structure_from_dashboard_config(Country.MX, dashboard)

    assert structure.source == "config_cache"
    assert structure.widgets
    assert structure.widgets[0].widget_id.startswith("role:")


def test_dataset_entities_filter_by_dashboard_id(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    store.merge_raw_calls(
        "MX",
        [
            {
                "country": "MX",
                "source_endpoint": "/analytics",
                "range_key": "last_7_days",
                "dashboard_id": dashboard_id,
                "card_id": f"card-{dashboard_id}",
                "card_type": "CHART",
                "view_name": "coreMetrics",
                "metric_ids": "[]",
                "query_hash": f"query-{dashboard_id}",
                "response_hash": f"response-{dashboard_id}",
                "source_ts_start": "2026-06-24T00:00:00Z",
                "source_ts_end": "2026-06-30T05:59:00Z",
                "row_count": 1,
            }
            for dashboard_id in ("dash-a", "dash-b")
        ],
    )

    entities = store.list_country_entities("MX", dashboard_id="dash-a")
    raw_calls = next(entity for entity in entities if entity["id"].endswith("raw_api_calls"))

    assert raw_calls["dashboard_id"] == "dash-a"
    assert raw_calls["rows"] == 1


def test_card_detail_filters_widgets_by_dashboard_id(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    store.write_country_dataset(
        "MX",
        range_dataset_path(DATASET_SUMMARY_WIDGETS, "last_7_days"),
        [
            _summary_widget_row("dash-a", "Dashboard A", 10),
            _summary_widget_row("dash-b", "Dashboard B", 20),
        ],
    )

    detail = LocalDashboardService(store).card_detail(
        "MX",
        "summary.page_views",
        range_key="last_7_days",
        dashboard_id="dash-b",
    )

    assert detail["dashboard_id"] == "dash-b"
    assert detail["value"] == 20
    assert detail["widget"]["dashboard_name"] == "Dashboard B"


def test_manual_dashboard_routes_are_not_exposed() -> None:
    paths = {getattr(route, "path", "") for route in app.routes}

    assert "/api/quantum/discover-dashboard" not in paths
    assert "/api/quantum/test-dashboard" not in paths


def test_dataset_regression_route_forwards_dashboard_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class Report:
        def model_dump(self, *, mode: str) -> dict[str, object]:
            captured["mode"] = mode
            return {"status": "passed"}

    def fake_run_regression(*args: object, **kwargs: object) -> Report:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Report()

    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    monkeypatch.setattr(routes, "run_regression", fake_run_regression)

    response = routes.run_dataset_regression(
        "MX",
        store,
        dashboard_id="dash-a",
        range_key="last_7_days",
    )

    assert response == {"status": "passed"}
    assert captured["kwargs"] == {"dashboard_id": "dash-a", "range_key": "last_7_days"}
    assert captured["mode"] == "json"


def _summary_widget_row(
    dashboard_id: str,
    dashboard_name: str,
    value: int,
) -> dict[str, object]:
    return {
        "id": "summary.page_views",
        "card_role": "summary.page_views",
        "dashboard_id": dashboard_id,
        "dashboard_name": dashboard_name,
        "range_key": "last_7_days",
        "title": "Paginas vistas",
        "value": value,
        "unit": "count",
        "period_start": "2026-06-24T06:00:00Z",
        "period_end": "2026-06-30T05:59:00Z",
        "period_timezone": "CST",
        "chart_payload": {
            "series": [
                {
                    "label": "Mobile",
                    "points": [{"ts": "2026-06-24T06:00:00Z", "label": "Jun 24", "value": value}],
                }
            ],
        },
    }


class _Session:
    def __init__(self, **values: object) -> None:
        self.__dict__.update(values)
