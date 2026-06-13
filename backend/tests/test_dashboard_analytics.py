from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.analytics.service import AnalyticsService
from backend.app.api import routes
from backend.app.api.routes import config_store_dep, parquet_store_dep, settings_dep
from backend.app.config.settings import Settings
from backend.app.main import app
from backend.app.quantum.config_store import QuantumConfigStore
from backend.app.storage.parquet_store import ParquetStore


@pytest.fixture()
def client(tmp_path: Path) -> Generator[TestClient]:
    settings = Settings(qm_data_dir=tmp_path)
    app.dependency_overrides[settings_dep] = lambda: settings
    app.dependency_overrides[config_store_dep] = lambda: QuantumConfigStore(settings)
    app.dependency_overrides[parquet_store_dep] = lambda: ParquetStore(settings)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_countries_without_data(client: TestClient) -> None:
    response = client.get("/api/analytics/countries")

    assert response.status_code == 200
    payload = response.json()
    assert payload["default_country"] == "MX"
    assert [country["code"] for country in payload["countries"]] == ["ES", "MX", "PE", "CO", "AR"]
    assert all(country["has_data"] is False for country in payload["countries"])


def test_countries_with_one_and_multiple_data(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    _write_sample_raw_calls(store, "MX", "mx-1")

    one_country = AnalyticsService(store).countries()
    assert one_country["default_country"] == "MX"
    assert _country(one_country, "MX")["has_data"] is True

    _write_sample_raw_calls(store, "ES", "es-1")
    multiple_countries = AnalyticsService(store).countries()
    assert multiple_countries["default_country"] == "ES"
    assert _country(multiple_countries, "ES")["raw_calls"] == 1


def test_summary_empty_without_parquet(client: TestClient) -> None:
    response = client.get("/api/analytics/dashboard/summary?country=MX")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "empty"
    assert payload["widgets"] == []
    assert payload["required_dataset"] == "raw_api_calls"


def test_summary_empty_with_unparseable_rows(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    store.write_raw_calls("MX", [_raw_call("MX", "mx-empty", {"rows": []})])

    payload = AnalyticsService(store).dashboard_summary("MX")

    assert payload["status"] == "empty"
    assert "parseable analytics rows" in str(payload["reason"])


def test_summary_from_parseable_rows_dimension_and_segment(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    _write_sample_raw_calls(store, "MX", "mx-1")
    service = AnalyticsService(store)

    summary = service.dashboard_summary("MX")
    widgets = {widget["id"]: widget for widget in summary["widgets"]}

    assert summary["status"] == "ok"
    assert widgets["page_views"]["value"] == 150
    assert widgets["sessions"]["value"] == 30
    assert widgets["converted_sessions"]["value"] == 3
    assert widgets["avg_session_time"]["value"] == 86.67

    dimensioned = service.dashboard_summary("MX", dimension="browser")
    assert dimensioned["applied_dimension"] == {"id": "browser", "label": "Browser"}
    browser_breakdown = {item["label"] for item in dimensioned["widgets"][0]["breakdown"]}
    assert browser_breakdown == {"Safari", "Chrome"}

    segmented = service.dashboard_summary("MX", segment="app_name:pagos")
    segmented_widgets = {widget["id"]: widget for widget in segmented["widgets"]}
    assert segmented["applied_segment"]["label"] == "App Name: pagos"
    assert segmented_widgets["sessions"]["value"] == 10


def test_summary_table_search_sort_and_country_without_data(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    _write_sample_raw_calls(store, "MX", "mx-1")
    service = AnalyticsService(store)

    searched = service.dashboard_summary_table("MX", search="porta")
    assert searched["status"] == "ok"
    assert [row["name"] for row in searched["rows"]] == ["portabilidad nomina"]

    asc = service.dashboard_summary_table("MX", sort="page_views", direction="asc")
    assert [row["page_views"] for row in asc["rows"]] == [50, 100]

    empty_country = service.dashboard_summary_table("PE")
    assert empty_country["status"] == "empty"
    assert empty_country["rows"] == []


def test_errors_dashboard_and_table(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    _write_sample_raw_calls(store, "MX", "mx-1")
    service = AnalyticsService(store)

    dashboard = service.dashboard_errors("MX")
    widgets = {widget["id"]: widget for widget in dashboard["widgets"]}

    assert dashboard["status"] == "ok"
    assert widgets["error_sessions_by_app_name"]["total"] == 5
    assert widgets["error_sessions_by_app_name"]["series"][0]["name"] == "portabilidad nomina"
    assert widgets["error_session_percentage_by_app_name"]["rows"][0]["error_session_percent"] == 20

    table = service.dashboard_errors_table("MX", sort="error_session_percent", direction="asc")
    assert [row["error_session_percent"] for row in table["rows"]] == [10, 20]


def test_dimensions_and_segments_are_inferred_from_local_data(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    _write_sample_raw_calls(store, "MX", "mx-1")
    service = AnalyticsService(store)

    dimensions = service.dimensions("MX")
    groups = {group["label"]: group["items"] for group in dimensions["groups"]}
    assert any(item["id"] == "app_name" for item in groups["Page"])
    assert any(item["id"] == "browser" for item in groups["Device"])

    segments = service.segments("MX")
    segment_ids = {segment["id"] for segment in segments["segments"]}
    assert "app_name:pagos" in segment_ids
    assert "browser:Safari" in segment_ids
    assert "error_state:with_error" in segment_ids


def test_analytics_endpoints_do_not_call_quantum_or_leak_secrets(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_quantum_client(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("QuantumClient must not be used by offline analytics endpoints.")

    monkeypatch.setattr(routes, "QuantumClient", fail_quantum_client)

    for path in [
        "/api/analytics/countries",
        "/api/analytics/dashboard/summary?country=MX",
        "/api/analytics/dashboard/summary/table?country=MX",
        "/api/analytics/dashboard/errors?country=MX",
        "/api/analytics/dashboard/errors/table?country=MX",
        "/api/analytics/dimensions?country=MX",
        "/api/analytics/segments?country=MX",
    ]:
        response = client.get(path)
        assert response.status_code == 200
        body = json.dumps(response.json())
        assert "Authorization" not in body
        assert "Cookie" not in body
        assert "session=" not in body


def test_legacy_array_rows_remain_readable(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    response_json = {
        "columns": ["App Name", "Operating System", "Page Views", "Sessions"],
        "rows": [["legacy app", "iOS", 7, 3]],
    }
    store.write_raw_calls("MX", [_raw_call("MX", "legacy-1", response_json)])

    table = AnalyticsService(store).dashboard_summary_table("MX")

    assert table["status"] == "ok"
    assert table["rows"][0]["name"] == "legacy app"
    assert table["rows"][0]["page_views"] == 7


def _country(payload: dict[str, Any], code: str) -> dict[str, Any]:
    return next(country for country in payload["countries"] if country["code"] == code)


def _write_sample_raw_calls(store: ParquetStore, country: str, ingestion_id: str) -> None:
    response_json = {
        "rows": [
            {
                "App Name": "portabilidad nomina",
                "Operating System": "iOS",
                "Application Type": "Mobile",
                "Browser": "Safari",
                "Page Views": 100,
                "Sessions": 20,
                "General - Conversiones": 3,
                "Average Session Duration": 80,
                "Sessions with Error": 4,
            },
            {
                "App Name": "pagos",
                "Operating System": "Android",
                "Application Type": "Mobile",
                "Browser": "Chrome",
                "Page Views": 50,
                "Sessions": 10,
                "General - Conversiones": 0,
                "Average Session Duration": 100,
                "Sessions with Error": 1,
                "error_session_percent": 10,
            },
        ]
    }
    store.write_raw_calls(country, [_raw_call(country, ingestion_id, response_json)])


def _raw_call(country: str, ingestion_id: str, response_json: dict[str, Any]) -> dict[str, Any]:
    request_json = {
        "dimensions": {
            "dimensions": [
                {"id": "app_name", "label": "App Name"},
                {"id": "operating_system", "label": "Operating System"},
                {"id": "browser", "label": "Browser"},
            ]
        },
        "metrics": {"metrics": ["page_views", "sessions"]},
        "metadata": {
            "dashboardId": "dash",
            "cardId": "card",
            "cardType": "TABLE",
            "viewName": "coreMetrics",
            "metricIds": ["page_views", "sessions"],
        },
    }
    rows = response_json.get("rows")
    row_count = len(rows) if isinstance(rows, list) else 0
    return {
        "ingestion_id": ingestion_id,
        "ingestion_ts": "2026-06-12T00:00:00Z",
        "country": country,
        "source_endpoint": "/analytics",
        "http_method": "POST",
        "status_code": 200,
        "dashboard_id": "dash",
        "card_id": "card",
        "card_type": "TABLE",
        "view_name": "coreMetrics",
        "metric_ids": json.dumps(["page_views", "sessions"]),
        "query_hash": f"query-{ingestion_id}",
        "response_hash": f"response-{ingestion_id}",
        "request_json": json.dumps(request_json),
        "response_json": json.dumps(response_json),
        "row_count": row_count,
        "source_ts_start": "2026-06-01T00:00:00Z",
        "source_ts_end": "2026-06-12T00:00:00Z",
    }
