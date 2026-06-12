from pathlib import Path

from backend.app.config.settings import Settings
from backend.app.quantum.config_store import QuantumConfigStore
from backend.app.quantum.schemas import BrowserName, Country, QuantumConfigUpdate, SessionMode


def test_config_store_does_not_persist_manual_cookie(tmp_path: Path) -> None:
    settings = Settings(qm_data_dir=tmp_path)
    store = QuantumConfigStore(settings)

    saved = store.write(
        QuantumConfigUpdate(
            browser=BrowserName.chrome,
            base_url="https://bbvamx.quantummetric.com",
            session_mode=SessionMode.manual,
            country=Country.MX,
            dashboard_url="https://bbvamx.quantummetric.com/#/dashboard/demo",
            verify_tls=True,
            manual_cookie="session=secret",
        )
    )

    text = store.path.read_text()
    assert saved.session_mode == "manual"
    assert "secret" not in text
    assert "manual_cookie" not in text
