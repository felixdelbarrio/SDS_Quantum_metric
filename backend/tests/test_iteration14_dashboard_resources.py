from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from backend.app.api import routes
from backend.app.auth.browser_cookies import BrowserCookieProvider
from backend.app.config.settings import Settings
from backend.app.quantum.config_store import QuantumConfigStore
from backend.app.quantum.schemas import (
    Country,
    QuantumConfigUpdate,
    QuantumCountryConfig,
    QuantumDashboardConfig,
)
from backend.app.quantum_dashboard.dashboard_resources import (
    DashboardResourcesError,
    DashboardResourcesResult,
    fetch_dashboard_resources,
    read_dashboard_resources_cache,
    result_from_resources_payloads,
    write_dashboard_resources_cache,
)
from backend.app.quantum_dashboard.dashboard_structure import structure_from_payloads
from backend.app.quantum_dashboard.manual_dashboard import parse_dashboard_url

FIXTURES = Path(__file__).parent / "fixtures" / "quantum"


def test_resources_list_fixture_parses_14_dashboards_and_visible_names() -> None:
    payload = json.loads((FIXTURES / "dashboard_resources_list.json").read_text())

    result = result_from_resources_payloads(
        [payload],
        country=Country.CO,
        source="quantum_graphql",
    )

    assert result.total_count == 14
    assert len(result.resources) == 14
    dashboard = next(item for item in result.resources if item.name == "Dashboard General CO")
    assert dashboard.dashboard_id == "396a586b-2151-4b14-b7e1-5a316712f4f5"
    assert dashboard.name != dashboard.dashboard_id
    assert all(item.type == "DASHBOARD" for item in result.resources)
    assert len(result.dashboards) == 14


def test_dashboard_resources_result_accepts_dashboards_alias() -> None:
    result = DashboardResourcesResult.model_validate(
        {
            "country": "CO",
            "total_count": 1,
            "dashboards": [
                {
                    "dashboard_id": "dash-co",
                    "name": "Dashboard CO",
                    "type": "DASHBOARD",
                    "starred": False,
                    "country": "CO",
                    "source": "quantum_graphql",
                    "order": 0,
                }
            ],
        }
    )

    assert result.resources[0].name == "Dashboard CO"
    assert result.dashboards[0].dashboard_id == "dash-co"


def test_refresh_route_persists_all_graphql_dashboards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(qm_data_dir=tmp_path)
    store = QuantumConfigStore(settings)
    config = QuantumConfigUpdate(
        browser=store.default().browser,
        session_mode=store.default().session_mode,
        country=Country.CO,
        countries=[
            QuantumCountryConfig(
                country=Country.CO,
                base_url="https://bbvaco.quantummetric.com",
                enabled=True,
                dashboards=[],
            )
        ],
        verify_tls=True,
    )
    store.write(config)
    fixture = json.loads((FIXTURES / "dashboard_resources_list.json").read_text())

    def fake_fetch(**kwargs: Any) -> tuple[DashboardResourcesResult, None]:
        assert kwargs["country"] == Country.CO
        assert kwargs["base_url"] == "https://bbvaco.quantummetric.com"
        return (
            result_from_resources_payloads(
                [fixture],
                country=Country.CO,
                source="quantum_graphql",
            ),
            None,
        )

    monkeypatch.setattr(routes, "fetch_dashboard_resources_via_browser", fake_fetch)

    response = routes.refresh_country_quantum_dashboards(
        "CO",
        store,
        settings,
        _unused_cookie_provider(),
    )

    dashboards = cast(list[dict[str, Any]], response["dashboards"])
    assert response["total_count"] == 14
    assert len(dashboards) == 14
    assert dashboards[0]["dashboard_id"] == "7f2bed19-cf79-4394-8cdd-7831435f88ab"
    assert dashboards[0]["name"] == "Page Analysis"
    saved = store.read().required_country_config(Country.CO)
    assert len(saved.dashboards) == 14
    assert saved.dashboards[0].name == "Page Analysis"
    cached = read_dashboard_resources_cache(
        Country.CO,
        cache_dir=settings.config_dir / "dashboard_resources",
    )
    assert cached is not None
    assert len(cached.resources) == 14


def test_refresh_route_materializes_unsaved_country_from_action_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(qm_data_dir=tmp_path)
    store = QuantumConfigStore(settings)
    fixture = json.loads((FIXTURES / "dashboard_resources_list.json").read_text())

    def fake_fetch(**kwargs: Any) -> tuple[DashboardResourcesResult, None]:
        assert kwargs["country"] == Country.CO
        assert kwargs["base_url"] == "https://bbvaco.quantummetric.com"
        return (
            result_from_resources_payloads(
                [fixture],
                country=Country.CO,
                source="quantum_graphql",
            ),
            None,
        )

    monkeypatch.setattr(routes, "fetch_dashboard_resources_via_browser", fake_fetch)

    response = routes.refresh_country_quantum_dashboards(
        "CO",
        store,
        settings,
        _unused_cookie_provider(),
        request=routes.CountryActionRequest(base_url="https://bbvaco.quantummetric.com"),
    )

    saved = store.read().required_country_config(Country.CO)
    assert response["total_count"] == 14
    assert len(saved.dashboards) == 14
    assert saved.base_url == "https://bbvaco.quantummetric.com"
    assert saved.dashboards[0].name == "Page Analysis"


@pytest.mark.asyncio
async def test_fetch_dashboard_resources_paginates_dedupes_and_writes_cache(
    tmp_path: Path,
) -> None:
    page_one = {
        "data": {
            "resources": {
                "totalCount": 3,
                "resources": [
                    {
                        "id": "dash-a",
                        "type": "DASHBOARD",
                        "name": "Dashboard A",
                        "starred": False,
                    },
                    {
                        "id": "dash-b",
                        "type": "DASHBOARD",
                        "name": "Dashboard B",
                        "starred": True,
                    },
                ],
            }
        }
    }
    page_two = {
        "data": {
            "resources": {
                "totalCount": 3,
                "resources": [
                    {
                        "id": "dash-b",
                        "type": "DASHBOARD",
                        "name": "Dashboard B",
                        "starred": True,
                    },
                    {
                        "id": "dash-c",
                        "type": "DASHBOARD",
                        "name": "Dashboard C",
                        "starred": False,
                    },
                ],
            }
        }
    }
    session = _GraphQLSession(tmp_path, [page_one, page_two])

    result = await fetch_dashboard_resources(
        Country.MX,
        "https://bbvamx.quantummetric.com",
        session,
        force_refresh=True,
        page_size=2,
    )

    assert [item.dashboard_id for item in result.resources] == [
        "dash-a",
        "dash-b",
        "dash-c",
    ]
    assert len(session.requests) == 2
    assert session.requests[0]["variables"]["pagination"]["first"] == 0
    assert session.requests[1]["variables"]["pagination"]["first"] == 2
    assert read_dashboard_resources_cache(Country.MX, cache_dir=tmp_path) is not None


@pytest.mark.asyncio
async def test_fetch_dashboard_resources_falls_back_to_cache_without_secrets(
    tmp_path: Path,
) -> None:
    cached = result_from_resources_payloads(
        [
            {
                "data": {
                    "resources": {
                        "totalCount": 1,
                        "resources": [
                            {
                                "id": "dash-cache",
                                "type": "DASHBOARD",
                                "name": "Dashboard Cache",
                                "starred": False,
                            }
                        ],
                    }
                }
            }
        ],
        country=Country.MX,
        source="quantum_graphql",
    )
    write_dashboard_resources_cache(cached, cache_dir=tmp_path)

    result = await fetch_dashboard_resources(
        Country.MX,
        "https://bbvamx.quantummetric.com",
        _FailingGraphQLSession(tmp_path),
        force_refresh=True,
    )

    assert result.from_cache is True
    assert result.resources[0].name == "Dashboard Cache"
    cache_text = (tmp_path / "MX.json").read_text()
    assert "authorization" not in cache_text.casefold()
    assert "cookie" not in cache_text.casefold()


@pytest.mark.asyncio
async def test_fetch_dashboard_resources_errors_without_session_or_cache(
    tmp_path: Path,
) -> None:
    with pytest.raises(DashboardResourcesError):
        await fetch_dashboard_resources(
            Country.MX,
            "https://bbvamx.quantummetric.com",
            _FailingGraphQLSession(tmp_path),
            force_refresh=True,
        )


def test_parse_manual_dashboard_colombia_url() -> None:
    parsed = parse_dashboard_url(
        "https://bbvaco.quantummetric.com/#/dashboard/"
        "fccfa9f6-5d01-47cf-9ba6-b7bccd4d4f2b"
        "?dashboardUseGlobal=true&teamID=24feba5b-307d-40ed-83de-478111f8938e"
        "&ts=last_7_days"
    )

    assert parsed.dashboard_id == "fccfa9f6-5d01-47cf-9ba6-b7bccd4d4f2b"
    assert parsed.team_id == "24feba5b-307d-40ed-83de-478111f8938e"
    assert parsed.base_url == "https://bbvaco.quantummetric.com"
    assert parsed.range_key == "last_7_days"


def test_parse_manual_dashboard_accepts_raw_id() -> None:
    from backend.app.quantum_dashboard.manual_dashboard import parse_dashboard_url_or_id

    parsed = parse_dashboard_url_or_id("fccfa9f6-5d01-47cf-9ba6-b7bccd4d4f2b")

    assert parsed.dashboard_id == "fccfa9f6-5d01-47cf-9ba6-b7bccd4d4f2b"
    assert parsed.team_id is None


def test_dashboard_structure_fixture_separates_summary_and_errors() -> None:
    payload = json.loads((FIXTURES / "dashboard_structure_dashboard-general-mx.json").read_text())

    structure = structure_from_payloads(
        [payload],
        country=Country.MX,
        dashboard_id="dash-general-mx",
        team_id="team-mx",
        source="quantum_web",
    )

    assert [tab.name for tab in structure.tabs] == ["Resumen", "Errores"]
    widgets_by_title = {widget.title: widget for widget in structure.widgets}
    assert widgets_by_title["Paginas vistas"].tab_name == "Resumen"
    assert widgets_by_title["Evolutivo - % Sesiones con Error"].tab_name == "Errores"
    assert widgets_by_title["Top 20 Errores por nombre del error"].widget_type == "table"


def test_legacy_dashboard_name_is_not_replaced_with_id() -> None:
    dashboard = QuantumDashboardConfig(
        dashboard_id="dash-id",
        name="Dashboard default",
        is_default=True,
        validated=True,
    )

    assert dashboard.name == ""


def test_legacy_dashboard_name_equal_to_id_is_cleared() -> None:
    dashboard = QuantumDashboardConfig(
        dashboard_id="8e53eb82-587c-4b92-a0fa-0f6283677e28",
        name="8e53eb82-587c-4b92-a0fa-0f6283677e28",
        is_default=True,
        validated=True,
    )

    assert dashboard.name == ""


class _GraphQLSession:
    def __init__(self, cache_dir: Path, responses: list[dict[str, Any]]) -> None:
        self.dashboard_resources_cache_dir = cache_dir
        self.user_id = "user-test"
        self.responses = responses
        self.requests: list[dict[str, Any]] = []

    async def post_graphql(self, _endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(payload)
        return self.responses.pop(0)


class _FailingGraphQLSession:
    def __init__(self, cache_dir: Path) -> None:
        self.dashboard_resources_cache_dir = cache_dir


class _UnusedCookieProvider:
    def load(self, _browser: str, _base_url: str) -> list[Any]:
        return []


def _unused_cookie_provider() -> BrowserCookieProvider:
    return cast(BrowserCookieProvider, _UnusedCookieProvider())
