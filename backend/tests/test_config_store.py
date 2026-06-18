from pathlib import Path

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


def test_config_store_default_ingestion_depth_is_30_days(tmp_path: Path) -> None:
    settings = Settings(qm_data_dir=tmp_path)
    store = QuantumConfigStore(settings)

    assert store.default().ingestion_depth_days == 30


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
    assert loaded.schema_version == 2
    assert loaded.theme_preference == "light"
    assert dashboard is not None
    assert dashboard.dashboard_id == "dash"
    assert dashboard.widgets[0].widget_id == "card-1"
    assert dashboard.widgets[0].enabled is False
