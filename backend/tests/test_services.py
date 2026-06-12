from pathlib import Path
from typing import Any, cast

from backend.app.analytics.service import AnalyticsService
from backend.app.auth.session_store import SessionSecretStore
from backend.app.config.settings import Settings
from backend.app.quantum.config_store import QuantumConfigStore
from backend.app.quantum.schemas import QuantumConfigUpdate
from backend.app.storage.parquet_store import ParquetStore


def test_session_secret_store_clear() -> None:
    store = SessionSecretStore()
    store.set_manual_cookie("session=secret")
    assert store.get_manual_cookie() == "session=secret"
    store.clear()
    assert store.get_manual_cookie() is None


def test_config_store_default_and_delete(tmp_path: Path) -> None:
    settings = Settings(qm_data_dir=tmp_path)
    store = QuantumConfigStore(settings)
    assert store.read().country == "MX"
    store.write(QuantumConfigUpdate.model_validate(store.default().model_dump()))
    assert store.path.exists()
    store.delete()
    assert not store.path.exists()


def test_analytics_service_empty(tmp_path: Path) -> None:
    service = AnalyticsService(ParquetStore(Settings(qm_data_dir=tmp_path)))
    assert service.summary()["raw_calls"] == 0
    assert service.timeseries()["source"] == "parquet"
    assert service.table()["source"] == "parquet"
    filters = service.filters()["filters"]
    assert isinstance(filters, list)
    first = cast(dict[str, Any], filters[0])
    assert first["name"] == "country"
