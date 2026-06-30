from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.app.api.routes import (
    config_store_dep,
    ingestion_service_dep,
    parquet_store_dep,
    settings_dep,
)
from backend.app.config.settings import Settings
from backend.app.main import app
from backend.app.quantum.config_store import QuantumConfigStore
from backend.app.runtime import API_SCHEMA_VERSION, APP_ID
from backend.app.storage.parquet_store import ParquetStore


def test_health_and_config(tmp_path: Path) -> None:
    settings = Settings(qm_data_dir=tmp_path)
    app.dependency_overrides[settings_dep] = lambda: settings
    app.dependency_overrides[config_store_dep] = lambda: QuantumConfigStore(settings)
    app.dependency_overrides[parquet_store_dep] = lambda: ParquetStore(settings)
    client = TestClient(app)

    health = client.get("/api/health").json()
    assert health["status"] == "ok"
    assert health["app"] == APP_ID
    assert health["api_schema"] == API_SCHEMA_VERSION
    assert isinstance(health["pid"], int)
    response = client.get("/api/config/quantum")
    assert response.status_code == 200
    assert response.json()["country"] == "MX"
    assert response.json()["countries"][0]["country"] == "MX"

    app.dependency_overrides.clear()


def test_local_dashboard_coverage_endpoint_reports_missing_days(tmp_path: Path) -> None:
    settings = Settings(qm_data_dir=tmp_path)
    store = ParquetStore(settings)
    store.merge_raw_calls(
        "MX",
        [
            {
                "ingestion_id": "ing-coverage",
                "country": "MX",
                "source_endpoint": "/analytics",
                "dashboard_id": "dash",
                "card_id": "card",
                "card_type": "LINE",
                "view_name": "line",
                "metric_ids": "[]",
                "query_hash": "q",
                "response_hash": "r",
                "row_count": 1,
                "source_ts_start": "2026-06-18T06:00:00Z",
                "source_ts_end": "2026-06-19T05:59:59Z",
            }
        ],
    )
    app.dependency_overrides[settings_dep] = lambda: settings
    app.dependency_overrides[parquet_store_dep] = lambda: store
    client = TestClient(app)

    response = client.get(
        "/api/local-dashboard/coverage",
        params={"country": "MX", "start": "2026-06-17", "end": "2026-06-18"},
    )

    assert response.status_code == 200
    assert response.json()["complete"] is False
    assert response.json()["covered_days"] == ["2026-06-18"]
    assert response.json()["missing_days"] == ["2026-06-17"]

    app.dependency_overrides.clear()


def test_missing_days_endpoint_starts_async_job(tmp_path: Path) -> None:
    settings = Settings(qm_data_dir=tmp_path)
    app.dependency_overrides[settings_dep] = lambda: settings
    app.dependency_overrides[ingestion_service_dep] = lambda: _FakeIngestionService()
    client = TestClient(app)

    response = client.post(
        "/api/ingestions/missing-days",
        json={"country": "MX", "days": ["2026-06-17", "2026-06-18"]},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert response.json()["details"]["requested_days"] == ["2026-06-17", "2026-06-18"]

    app.dependency_overrides.clear()


def test_range_ingestion_endpoint_starts_async_job(tmp_path: Path) -> None:
    settings = Settings(qm_data_dir=tmp_path)
    fake_service = _FakeIngestionService()
    app.dependency_overrides[settings_dep] = lambda: settings
    app.dependency_overrides[ingestion_service_dep] = lambda: fake_service
    client = TestClient(app)

    response = client.post(
        "/api/ingestions/range",
        json={
            "country": "MX",
            "range_key": "last_7_days",
            "start_date": "2026-06-24",
            "end_date": "2026-06-30",
            "reason": "missing_days",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["reason"] == "missing_days"
    assert fake_service.last_request.range_key == "last_7_days"
    assert fake_service.last_request.start_date == "2026-06-24"
    assert fake_service.last_request.end_date == "2026-06-30"

    app.dependency_overrides.clear()


class _FakeIngestionService:
    last_request: Any

    def start(self, request: object) -> "_FakeJob":
        self.last_request = request
        return _FakeJob(request)

    def start_missing_days(self, request: object) -> "_FakeJob":
        self.last_request = request
        return _FakeJob(request)


class _FakeJob:
    def __init__(self, request: object) -> None:
        self.request = request

    def model_dump(self, mode: str) -> dict[str, object]:
        _ = mode
        return {
            "ingestion_id": "missing-days-job",
            "country": "MX",
            "status": "pending",
            "details": {"requested_days": getattr(self.request, "days", [])},
        }
