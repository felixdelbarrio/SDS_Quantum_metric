from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.api.routes import config_store_dep, parquet_store_dep, settings_dep
from backend.app.config.settings import Settings
from backend.app.main import app
from backend.app.quantum.config_store import QuantumConfigStore
from backend.app.storage.parquet_store import ParquetStore


def test_health_and_config(tmp_path: Path) -> None:
    settings = Settings(qm_data_dir=tmp_path)
    app.dependency_overrides[settings_dep] = lambda: settings
    app.dependency_overrides[config_store_dep] = lambda: QuantumConfigStore(settings)
    app.dependency_overrides[parquet_store_dep] = lambda: ParquetStore(settings)
    client = TestClient(app)

    assert client.get("/api/health").json() == {"status": "ok"}
    response = client.get("/api/config/quantum")
    assert response.status_code == 200
    assert response.json()["country"] == "MX"

    app.dependency_overrides.clear()
