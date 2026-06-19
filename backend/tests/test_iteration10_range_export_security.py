from __future__ import annotations

import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.api.routes import config_store_dep, parquet_store_dep, settings_dep
from backend.app.config.settings import Settings
from backend.app.main import app
from backend.app.quantum.config_store import QuantumConfigStore
from backend.app.quantum_dashboard.aggregation_rules import (
    aggregation_for_role,
    requires_quantum_range_contract,
)
from backend.app.quantum_dashboard.builder import build_derived_datasets
from backend.app.quantum_dashboard.regression import run_regression
from backend.app.quantum_dashboard.service import LocalDashboardService
from backend.app.storage.parquet_store import ParquetStore
from backend.tests.test_quantum_dashboard_iteration4 import _fixture_rows


def test_aggregation_rules_classify_non_additive_widgets() -> None:
    assert aggregation_for_role("summary.page_views") == "sum"
    assert aggregation_for_role("summary.avg_session_duration") == "weighted_average"
    assert aggregation_for_role("errors.error_sessions_percentage_evolution") == "ratio"
    assert requires_quantum_range_contract("errors.top_errors_by_error_name") is True


def test_range_key_isolates_yesterday_from_today(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    today_rows = [
        {
            **row,
            "range_key": "today",
            "range_start": "2026-06-18T06:00:00Z",
            "range_end": "2026-06-19T05:59:59Z",
            "capture_mode": "range_contract",
        }
        for row in _fixture_rows()
    ]
    yesterday_rows = [
        {
            **row,
            "response_json": _scaled_response(row["response_json"], 2),
            "range_key": "yesterday",
            "range_start": "2026-06-17T06:00:00Z",
            "range_end": "2026-06-18T05:59:59Z",
            "source_ts_start": "2026-06-17T06:00:00Z",
            "source_ts_end": "2026-06-18T05:59:59Z",
            "capture_mode": "range_contract",
        }
        for row in _fixture_rows()
    ]
    store.merge_raw_calls("MX", today_rows + yesterday_rows)

    build_derived_datasets(store, "MX", range_key="today")
    build_derived_datasets(store, "MX", range_key="yesterday")
    run_regression(store, "MX", range_key="today")
    run_regression(store, "MX", range_key="yesterday")

    service = LocalDashboardService(store)
    today = service.summary("MX", range_key="today")
    yesterday = service.summary("MX", range_key="yesterday")

    assert today["range_key"] == "today"
    assert yesterday["range_key"] == "yesterday"
    assert today["widgets"][0]["range_key"] == "today"
    assert yesterday["widgets"][0]["range_key"] == "yesterday"
    assert today["widgets"][0]["value"] != yesterday["widgets"][0]["value"]


def test_export_endpoint_creates_zip_in_requested_downloads_path(tmp_path: Path) -> None:
    settings = Settings(qm_data_dir=tmp_path / "data", qm_export_dir=tmp_path / "Downloads")
    store = ParquetStore(settings)
    store.merge_raw_calls(
        "MX",
        [
            {
                "ingestion_id": "ing-export",
                "country": "MX",
                "source_endpoint": "/analytics",
                "dashboard_id": "dash",
                "card_id": "card",
                "card_type": "LINE",
                "view_name": "line",
                "metric_ids": "[]",
                "query_hash": "q",
                "response_hash": "r",
                "request_json": "{}",
                "response_json": '{"rows":[]}',
                "row_count": 0,
                "source_ts_start": "2026-06-18T06:00:00Z",
                "source_ts_end": "2026-06-19T05:59:59Z",
            }
        ],
    )
    app.dependency_overrides[settings_dep] = lambda: settings
    app.dependency_overrides[config_store_dep] = lambda: QuantumConfigStore(settings)
    app.dependency_overrides[parquet_store_dep] = lambda: store
    client = TestClient(app)
    try:
        response = client.post("/api/datasets/export", json={"countries": ["MX"]})
        payload = response.json()
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert payload["status"] == "exported"
    exported = Path(str(payload["path"]))
    assert exported.parent == tmp_path / "Downloads"
    assert exported.exists()
    with zipfile.ZipFile(exported) as archive:
        names = archive.namelist()
        assert "manifest.json" in names
        assert any(name.startswith("parquet/country=MX/") for name in names)
        serialized = (
            "\n".join(names)
            + "\n"
            + "\n".join(
                archive.read(name).decode("utf-8", "ignore")
                for name in names
                if name.endswith(".json")
            )
        )
    assert "session=" not in serialized
    assert "authorization" not in serialized.casefold()


def test_default_config_uses_controlled_session_not_real_chrome(tmp_path: Path) -> None:
    settings = Settings(qm_data_dir=tmp_path)
    config = QuantumConfigStore(settings).default()

    assert config.session_mode == "controlled"


def _scaled_response(raw: object, multiplier: float) -> str:
    import json

    payload = json.loads(str(raw))

    def scale(value: object) -> object:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value * multiplier
        if isinstance(value, list):
            return [scale(item) for item in value]
        if isinstance(value, dict):
            return {key: scale(item) for key, item in value.items()}
        return value

    return json.dumps(scale(payload))
