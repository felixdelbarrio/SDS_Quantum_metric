from pathlib import Path

from pytest import MonkeyPatch

from backend.app.config.settings import Settings
from backend.app.quantum.config_store import QuantumConfigStore
from backend.app.quantum.schemas import (
    BrowserName,
    Country,
    QuantumConfigUpdate,
    QuantumCountryConfig,
    QuantumDashboardConfig,
    QuantumWidgetConfig,
    SessionMode,
)


def test_config_store_does_not_persist_manual_cookie(tmp_path: Path) -> None:
    settings = Settings(qm_data_dir=tmp_path)
    store = QuantumConfigStore(settings)

    saved = store.write(
        QuantumConfigUpdate(
            browser=BrowserName.chrome,
            session_mode=SessionMode.manual,
            country=Country.MX,
            countries=[
                QuantumCountryConfig(
                    country=Country.MX,
                    base_url="https://bbvamx.quantummetric.com",
                    dashboard_id="demo",
                    team_id="team",
                    tab=0,
                )
            ],
            verify_tls=True,
            manual_cookie="session=secret",
        )
    )

    text = store.path.read_text()
    assert saved.session_mode == "manual"
    assert "secret" not in text
    assert "manual_cookie" not in text


def test_config_store_default_ingestion_depth_is_30_days(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.delenv("QUANTUM_INGESTION_DEPTH_DAYS", raising=False)
    monkeypatch.chdir(tmp_path)
    settings = Settings(qm_data_dir=tmp_path)
    store = QuantumConfigStore(settings)

    assert store.default().ingestion_depth_days == 30


def test_config_store_write_never_mutates_environment_file(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    env_path = tmp_path / ".env"
    env_path.write_text("KEEP_THIS=unchanged\n")
    store = QuantumConfigStore(Settings(qm_data_dir=tmp_path / "data"))

    store.write(
        QuantumConfigUpdate(
            browser=BrowserName.chrome,
            session_mode=SessionMode.browser,
            country=Country.CO,
            countries=[
                QuantumCountryConfig(
                    country=Country.CO,
                    base_url="https://bbvaco.quantummetric.com",
                    dashboard_id="demo",
                    team_id="team",
                    tab=0,
                )
            ],
            verify_tls=True,
            ingestion_depth_days=30,
        )
    )

    assert env_path.read_text() == "KEEP_THIS=unchanged\n"


def test_config_store_persists_ingestion_depth_and_theme(tmp_path: Path) -> None:
    settings = Settings(qm_data_dir=tmp_path, quantum_ingestion_depth_days=180)
    store = QuantumConfigStore(settings)

    saved = store.write(
        QuantumConfigUpdate(
            browser=BrowserName.chrome,
            session_mode=SessionMode.browser,
            country=Country.MX,
            countries=[
                QuantumCountryConfig(
                    country=Country.MX,
                    base_url="https://bbvamx.quantummetric.com",
                    dashboard_id="demo",
                    team_id="team",
                    tab=0,
                )
            ],
            verify_tls=True,
            ingestion_depth_days=730,
            theme_preference="dark",
        )
    )
    loaded = store.read()

    assert saved.ingestion_depth_days == 730
    assert loaded.ingestion_depth_days == 730
    assert loaded.theme_preference == "dark"
    assert loaded.session_mode == "browser"


def test_config_store_migrates_persisted_controlled_session_to_browser(
    tmp_path: Path,
) -> None:
    settings = Settings(qm_data_dir=tmp_path)
    store = QuantumConfigStore(settings)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        """
{
  "schema_version": 2,
  "browser": "chrome",
  "session_mode": "controlled",
  "country": "MX",
  "countries": [
    {
      "country": "MX",
      "base_url": "https://bbvamx.quantummetric.com",
      "dashboard_id": "demo",
      "team_id": "team",
      "tab": 0,
      "enabled": true
    }
  ],
  "verify_tls": true
}
""".strip()
    )

    loaded = store.read()

    assert loaded.session_mode == "browser"
    assert '"session_mode": "browser"' in store.path.read_text()


def test_config_store_migrates_legacy_file_and_deletes_both_locations(tmp_path: Path) -> None:
    settings = Settings(qm_data_dir=tmp_path)
    store = QuantumConfigStore(settings)
    store.legacy_path.parent.mkdir(parents=True, exist_ok=True)
    store.legacy_path.write_text(
        '{"browser":"chrome","session_mode":"browser","country":"MX",'
        '"base_url":"https://bbvamx.quantummetric.com",'
        '"dashboard_url":"https://bbvamx.quantummetric.com/#/dashboard/demo?teamID=team&tab=1"}'
    )

    loaded = store.read()

    assert loaded.countries[0].dashboard_id == "demo"
    assert loaded.countries[0].team_id == "team"
    assert loaded.countries[0].dashboards[0].summary_tab == 1
    assert store.path.exists()

    store.delete()

    assert not store.path.exists()
    assert not store.legacy_path.exists()


def test_config_store_builds_countries_from_json_settings(tmp_path: Path) -> None:
    settings = Settings(
        qm_data_dir=tmp_path,
        qm_country="CO",
        qm_country_configs=(
            '[{"country":"CO","base_url":"https://bbvaco.quantummetric.com",'
            '"dashboard_id":"co-dashboard","team_id":"co-team","tab":2}]'
        ),
    )

    config = QuantumConfigStore(settings).default()

    assert config.country == Country.CO
    assert config.countries[0].dashboard_id == "co-dashboard"
    assert config.countries[0].dashboards[0].summary_tab == 2


def test_config_store_persists_dashboards_widgets_and_schema_version(tmp_path: Path) -> None:
    settings = Settings(qm_data_dir=tmp_path)
    store = QuantumConfigStore(settings)

    store.write(
        QuantumConfigUpdate(
            browser=BrowserName.chrome,
            session_mode=SessionMode.browser,
            country=Country.MX,
            countries=[
                QuantumCountryConfig(
                    country=Country.MX,
                    base_url="https://bbvamx.quantummetric.com",
                    dashboards=[
                        QuantumDashboardConfig(
                            dashboard_id="dash",
                            name="General",
                            team_id="team",
                            is_default=True,
                            validated=True,
                            validation_status="ok",
                            widgets=[
                                QuantumWidgetConfig(
                                    role="summary.page_views",
                                    title="Paginas vistas",
                                    widget_id="card-1",
                                    widget_type="CHART",
                                    tab="summary",
                                    enabled=False,
                                )
                            ],
                        )
                    ],
                )
            ],
            verify_tls=True,
            theme_preference="light",
        )
    )

    loaded = QuantumConfigStore(settings).read()
    country = loaded.required_country_config(Country.MX)
    dashboard = country.default_dashboard()

    assert store.path.name == "quantum_config.json"
    assert loaded.schema_version == 3
    assert loaded.theme_preference == "light"
    assert dashboard is not None
    assert dashboard.dashboard_id == "dash"
    assert dashboard.widgets[0].widget_id == "card-1"
    assert dashboard.widgets[0].enabled is False
