from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.app.api.routes import config_store_dep, parquet_store_dep, settings_dep
from backend.app.config.settings import Settings
from backend.app.main import app
from backend.app.quantum.config_store import QuantumConfigStore
from backend.app.quantum.schemas import Country, QuantumCountryConfig
from backend.app.quantum_dashboard.builder import build_derived_datasets
from backend.app.quantum_dashboard.card_mapper import map_card_role
from backend.app.quantum_dashboard.catalog import SUMMARY_DETAIL_TABLE
from backend.app.quantum_dashboard.discovery import (
    discover_dashboard_from_config,
    parse_dashboard_url,
)
from backend.app.quantum_dashboard.parsers import (
    build_line_chart_payload_from_series,
    parse_card,
)
from backend.app.quantum_dashboard.regression import run_regression
from backend.app.quantum_dashboard.service import LocalDashboardService
from backend.app.storage.parquet_store import ParquetStore

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "quantum_dashboard"


def test_discovery_extracts_dashboard_team_and_tab_from_url() -> None:
    parsed = parse_dashboard_url(
        "https://bbvamx.quantummetric.com/#/dashboard/dash-123?tab=1&teamID=team-456"
    )

    assert parsed.dashboard_id == "dash-123"
    assert parsed.team_id == "team-456"
    assert parsed.tab == 1


def test_discovery_uses_env_defaults_as_fallback(tmp_path: Path) -> None:
    settings = Settings(
        qm_data_dir=tmp_path,
        quantum_default_dashboard_id="dash-default",
        quantum_default_team_id="team-default",
        quantum_default_summary_tab=0,
        quantum_default_errors_tab=1,
    )

    result = discover_dashboard_from_config(
        settings=settings,
        country_config=QuantumCountryConfig(country=Country.MX, base_url=""),
    )

    assert result.dashboard_id == "dash-default"
    assert result.team_id == "team-default"
    assert result.tabs == [
        {"name": "Resumen", "tab": 0, "role": "summary"},
        {"name": "Errores", "tab": 1, "role": "errors"},
    ]


def test_config_api_exposes_auditable_dashboard_widget_metadata(tmp_path: Path) -> None:
    settings = Settings(qm_data_dir=tmp_path)
    app.dependency_overrides[settings_dep] = lambda: settings
    app.dependency_overrides[config_store_dep] = lambda: QuantumConfigStore(settings)
    app.dependency_overrides[parquet_store_dep] = lambda: ParquetStore(settings)
    client = TestClient(app)
    try:
        payload = client.get("/api/config/quantum").json()
    finally:
        app.dependency_overrides.clear()

    assert payload["countries"][0]["dashboard_resolved"] is True
    dashboard = payload["countries"][0]["dashboards"][0]
    assert dashboard["dashboard_id"]
    assert dashboard["team_id"]
    assert dashboard["widgets"][0]["role"] == "summary.page_views"
    assert dashboard["widgets"][0]["widget_type"] == "CHART"


def test_builder_persists_contracts_snapshots_derived_and_no_cookies(tmp_path: Path) -> None:
    store = _store_with_fixtures(tmp_path)

    result = build_derived_datasets(store, "MX")

    assert result.regression_status == "passed"
    assert result.mandatory_cards_captured == 9
    assert result.derived_datasets == 7
    contracts = store.read_country_dataset("MX", "visual_contracts")
    snapshots = store.read_country_dataset("MX", "web_snapshots")
    summary = store.read_country_dataset("MX", "derived/summary_widgets")
    chart_payloads = store.read_country_dataset("MX", "derived/chart_payloads")
    detail = store.read_country_dataset("MX", "derived/summary_detail_table")
    assert {row["visual_role"] for row in contracts} >= {
        "summary.page_views",
        "errors.top_errors_by_error_name",
    }
    assert snapshots[0]["card_role"]
    assert next(row for row in summary if row["id"] == "page_views")["value"] == 150
    assert next(row for row in summary if row["id"] == "page_views")["chart_payload"]["series"]
    assert chart_payloads
    assert detail[0]["app_name"] == "portabilidad nomina"
    assert any(row.get("parent_row_id") for row in detail)
    all_payload = json.dumps(
        {
            "contracts": contracts,
            "snapshots": snapshots,
            "summary": summary,
            "detail": detail,
        }
    )
    assert "Cookie" not in all_payload
    assert "Authorization" not in all_payload
    assert "session=" not in all_payload


def test_regression_passes_and_writes_report(tmp_path: Path) -> None:
    store = _store_with_fixtures(tmp_path)
    build_derived_datasets(store, "MX")

    report = run_regression(store, "MX", ingestion_id="fixture-ingestion")

    assert report.verdict == "PASSED"
    assert report.status == "passed"
    assert len(report.cards) == 9
    assert (store.settings.reports_dir / "regression/latest-web-vs-local.md").exists()


def test_builder_uses_capture_chunk_range_when_source_range_is_missing(
    tmp_path: Path,
) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    rows = [
        {
            **row,
            "source_ts_start": None,
            "source_ts_end": None,
            "capture_chunk_start": "2026-06-18T06:00:00Z",
            "capture_chunk_end": "2026-06-19T05:59:59Z",
        }
        for row in _fixture_rows()
    ]
    store.merge_raw_calls("MX", rows)

    result = build_derived_datasets(store, "MX")

    assert not [
        error
        for error in result.parser_errors
        if error["error_code"] == "failed_period_label_mismatch"
    ]
    chart_payloads = store.read_country_dataset("MX", "derived/chart_payloads")
    assert chart_payloads
    assert all(row["period_label"] for row in chart_payloads)


def test_regression_allows_parent_only_summary_table_when_web_has_no_children(
    tmp_path: Path,
) -> None:
    store = _store_with_fixtures(tmp_path)
    build_derived_datasets(store, "MX")
    summary_rows = store.read_country_dataset("MX", "derived/summary_detail_table")
    parent_rows = [row for row in summary_rows if not row.get("parent_row_id")]
    snapshots = []
    for snapshot in store.read_country_dataset("MX", "web_snapshots"):
        if snapshot.get("card_role") == "summary.detail_by_app_name_os":
            snapshot = {
                **snapshot,
                "visible_table_rows": parent_rows[:10],
            }
        snapshots.append(snapshot)
    store.write_country_dataset("MX", "derived/summary_detail_table", parent_rows)
    store.write_country_dataset(
        "MX",
        "web_snapshots",
        snapshots,
        file_name="web_snapshots.parquet",
    )

    report = run_regression(store, "MX")

    detail = next(
        card for card in report.cards if card.card_role == "summary.detail_by_app_name_os"
    )
    assert detail.status == "passed"


def test_regression_fails_when_mandatory_card_is_missing(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    rows = [row for row in _fixture_rows() if row["card_role"] != "errors.top_errors_by_error_name"]
    store.merge_raw_calls("MX", rows)

    build = build_derived_datasets(store, "MX")
    report = run_regression(store, "MX")

    assert "errors.top_errors_by_error_name" in build.missing_roles
    assert report.verdict == "FAILED"
    assert any(card.status == "failed_missing_card" for card in report.cards)


def test_local_dashboard_apis_read_derived_data_offline(tmp_path: Path) -> None:
    store = _store_with_fixtures(tmp_path)
    build_derived_datasets(store, "MX")
    run_regression(store, "MX")
    service = LocalDashboardService(store)

    status = service.status("MX")
    summary = service.summary("MX")
    summary_table = service.summary_table("MX", search="porta", sort="page_views")
    errors = service.errors("MX")
    top_errors = service.top_errors_table("MX", sort="error_sessions")
    app_name = service.app_name_error_table("MX", search="pagos")

    assert status["summary_ready"] is True
    assert status["errors_ready"] is True
    assert status["regression_status"] == "passed"
    assert [widget["id"] for widget in summary["widgets"]] == [
        "page_views",
        "sessions",
        "converted_sessions",
        "avg_session_duration",
    ]
    assert summary_table["rows"][0]["app_name"] == "portabilidad nomina"
    segmented = service.summary_table("MX", segment="app_name:portabilidad nomina")
    assert segmented["applied_segment"]["label"] == "App Name: portabilidad nomina"
    assert {row["app_name"] for row in segmented["rows"]} == {"portabilidad nomina"}
    outside_range = service.summary("MX", start_date="2030-01-01", end_date="2030-01-01")
    assert outside_range["status"] == "empty"
    assert {widget["id"] for widget in errors["widgets"]} >= {
        "error_sessions_percentage_evolution",
        "error_sessions_by_app_name",
    }
    donut = next(
        widget for widget in errors["widgets"] if widget["id"] == "error_sessions_by_app_name"
    )
    assert donut["value"] == donut["total"]
    assert donut["breakdown"]
    assert top_errors["rows"][0]["name"] == "TypeError"
    assert app_name["rows"][0]["name"] == "pagos"


def test_local_dashboard_rewrites_legacy_epoch_period_label(tmp_path: Path) -> None:
    store = _store_with_fixtures(tmp_path)
    build_derived_datasets(store, "MX")
    run_regression(store, "MX")
    rows = store.read_country_dataset("MX", "derived/summary_widgets")
    for row in rows:
        if row.get("card_role") == "summary.page_views":
            row["period_start"] = "1781676000"
            row["period_end"] = "1781686680"
            payload = dict(row["chart_payload"])
            payload["period_label"] = "1781676000 - 1781686680 CST"
            row["chart_payload"] = payload
    store.write_country_dataset("MX", "derived/summary_widgets", rows)

    summary = LocalDashboardService(store).summary("MX")
    widget = next(item for item in summary["widgets"] if item["role"] == "summary.page_views")

    assert widget["chart_payload"]["period_label"] != "1781676000 - 1781686680 CST"
    assert "1781676000" not in widget["chart_payload"]["period_label"]
    assert "CST" in widget["chart_payload"]["period_label"]


def test_local_dashboard_card_detail_breakdown_and_points(tmp_path: Path) -> None:
    store = _store_with_fixtures(tmp_path)
    build_derived_datasets(store, "MX")
    run_regression(store, "MX")
    service = LocalDashboardService(store)

    detail = service.card_detail("MX", "summary.page_views")
    breakdown = service.card_breakdown("MX", "summary.page_views")
    points = service.card_points("MX", "summary.page_views")

    assert detail["status"] == "ok"
    assert (
        detail["video_notice"] == "La reproduccion de sesiones solo esta disponible en Quantum Web."
    )
    assert detail["points"]
    assert breakdown["breakdown"]
    assert points["points"]


def test_dataset_entity_endpoints_are_paged_and_schema_is_available(tmp_path: Path) -> None:
    store = _store_with_fixtures(tmp_path)
    build_derived_datasets(store, "MX")
    run_regression(store, "MX")
    app.dependency_overrides[settings_dep] = lambda: store.settings
    app.dependency_overrides[config_store_dep] = lambda: QuantumConfigStore(store.settings)
    app.dependency_overrides[parquet_store_dep] = lambda: store
    client = TestClient(app)
    try:
        entities = client.get("/api/datasets/MX/entities").json()
        rows = client.get("/api/datasets/MX/entities/derived/chart_payloads?limit=1").json()
        schema = client.get("/api/datasets/MX/entities/derived/chart_payloads/schema").json()
    finally:
        app.dependency_overrides.clear()

    assert any(entity["id"] == "derived/chart_payloads" for entity in entities["entities"])
    assert rows["limit"] == 1
    assert rows["rows"]
    assert "chart_payload" in schema["schema"]


def test_regression_fails_when_chart_payload_is_missing(tmp_path: Path) -> None:
    store = _store_with_fixtures(tmp_path)
    build_derived_datasets(store, "MX")
    rows = store.read_country_dataset("MX", "derived/summary_widgets")
    for row in rows:
        if row.get("card_role") == "summary.page_views":
            row["chart_payload"] = None
    store.write_country_dataset("MX", "derived/summary_widgets", rows)

    report = run_regression(store, "MX")

    assert report.verdict == "FAILED"
    assert any(card.status == "failed_chart_contract_incomplete" for card in report.cards)


def test_summary_detail_parser_does_not_duplicate_parent_as_null_child() -> None:
    result = parse_card(
        {
            "response_json": json.dumps(
                {
                    "rows": [
                        {
                            "app_name": "affiliation basica",
                            "operating_system": None,
                            "page_views": 10,
                            "sessions": 3,
                            "conversions": 1,
                        },
                        {
                            "app_name": "affiliation basica",
                            "operating_system": "Android",
                            "page_views": 7,
                            "sessions": 2,
                            "conversions": 1,
                        },
                    ]
                }
            )
        },
        SUMMARY_DETAIL_TABLE,
    )

    rows = result.data["rows"]

    assert result.status == "ok"
    assert [row["depth"] for row in rows] == [0, 1]
    assert rows[0]["name"] == "affiliation basica"
    assert rows[1]["operating_system"] == "Android"


def test_summary_detail_parser_preserves_web_hierarchy() -> None:
    result = parse_card(
        {
            "response_json": json.dumps(
                {
                    "rows": [
                        {
                            "row_id": "app:pagos",
                            "parent_row_id": None,
                            "depth": 0,
                            "is_expandable": True,
                            "name": "pagos",
                            "app_name": "pagos",
                            "page_views": 10,
                        },
                        {
                            "row_id": "app:pagos:os:iOS",
                            "parent_row_id": "app:pagos",
                            "depth": 1,
                            "name": "iOS",
                            "app_name": "pagos",
                            "operating_system": "iOS",
                            "page_views": 6,
                        },
                    ]
                }
            )
        },
        SUMMARY_DETAIL_TABLE,
    )

    rows = result.data["rows"]

    assert result.status == "ok"
    assert len(rows) == 2
    assert rows[0]["row_id"] == "app:pagos"
    assert rows[1]["parent_row_id"] == "app:pagos"


def test_local_dashboard_endpoints_do_not_call_quantum(
    tmp_path: Path,
) -> None:
    store = _store_with_fixtures(tmp_path)
    build_derived_datasets(store, "MX")
    run_regression(store, "MX")
    app.dependency_overrides[settings_dep] = lambda: store.settings
    app.dependency_overrides[config_store_dep] = lambda: QuantumConfigStore(store.settings)
    app.dependency_overrides[parquet_store_dep] = lambda: store
    client = TestClient(app)
    try:
        for path in [
            "/api/local-dashboard/status?country=MX",
            "/api/local-dashboard/summary?country=MX",
            "/api/local-dashboard/summary/table?country=MX",
            "/api/local-dashboard/errors?country=MX",
            "/api/local-dashboard/errors/top-errors?country=MX",
            "/api/local-dashboard/errors/app-name?country=MX",
        ]:
            response = client.get(path)
            assert response.status_code == 200
            assert "quantummetric.com" not in json.dumps(response.json())
    finally:
        app.dependency_overrides.clear()


def test_real_quantum_card_mapper_uses_tab_card_type_metrics_and_dimensions() -> None:
    assert map_card_role(_real_call(tab="summary", card_type="TABLE")) == (
        "summary.detail_by_app_name_os"
    )
    assert (
        map_card_role(
            _real_call(
                tab="summary",
                card_type="CHART",
                metric_ids=["bde22d61-91c0-4d27-8ee3-ef467daea00c"],
            )
        )
        == "summary.page_views"
    )
    assert (
        map_card_role(
            _real_call(
                tab="summary",
                card_type="CHART",
                metric_ids=["2249fa52-8d15-46f4-b601-fc6d11958218"],
            )
        )
        == "summary.avg_session_duration"
    )
    assert (
        map_card_role(
            _real_call(
                tab="errors",
                card_type="TABLE",
                metric_ids=[
                    "519433db-1b8e-4989-ab29-6eca4492cf94",
                    "d450b2fd-26d7-4a9e-a076-199a9d51e1bb",
                ],
                dimension_path=["event", "event"],
            )
        )
        == "errors.top_errors_by_error_name"
    )
    assert (
        map_card_role(
            _real_call(
                tab="errors",
                card_type="TABLE",
                metric_ids=["519433db-1b8e-4989-ab29-6eca4492cf94"],
                dimension_path=["event_1", "mde_value"],
            )
        )
        == "errors.error_session_percentage_by_app_name"
    )
    assert (
        map_card_role(
            _real_call(
                tab="errors",
                card_type="CHART",
                metric_ids=["d450b2fd-26d7-4a9e-a076-199a9d51e1bb"],
                dimension_path=["event_1", "mde_value"],
            )
        )
        == "errors.error_sessions_by_app_name_comparison"
    )
    assert map_card_role(_summary_metric_shape_call(["hit", "id"])) == "summary.page_views"
    assert map_card_role(_summary_metric_shape_call(["session", "id"])) == "summary.sessions"
    assert (
        map_card_role(_summary_metric_shape_call(["session", "id"], filter_text="pagina exitosa"))
        == "summary.converted_sessions"
    )
    assert (
        map_card_role(
            _summary_metric_shape_call(
                ["session", "total_engaged_seconds"],
                aggregation=["qm", "default", "aggregations", "avg"],
            )
        )
        == "summary.avg_session_duration"
    )


def test_parsers_support_real_quantum_rows_and_results_shapes() -> None:
    widget = parse_card(
        _parser_call(
            response_json={"rows": [{"dimensions": None, "metrics": [65676]}]},
        ),
        "summary.page_views",
    )
    assert widget.status == "ok"
    assert widget.data["widget"]["value"] == 65676

    percent = parse_card(
        _parser_call(response_json={"rows": [{"dimensions": [], "metrics": [0.969]}]}),
        "errors.error_sessions_percentage_evolution",
    )
    assert percent.status == "ok"
    assert percent.data["widget"]["value"] == 97.0

    summary_table = parse_card(
        _parser_call(
            response_json={
                "rows": [
                    {"dimensions": ["pagos"], "metrics": [10, 2, 50]},
                    {"dimensions": ["portabilidad"], "metrics": [20, 3, 100]},
                ]
            }
        ),
        "summary.detail_by_app_name_os",
    )
    assert summary_table.status == "ok"
    assert summary_table.data["rows"][0]["sessions"] == 10
    assert summary_table.data["rows"][0]["conversions"] == 2
    assert summary_table.data["rows"][0]["page_views"] == 50

    top_errors = parse_card(
        _parser_call(
            response_json={
                "rows": [
                    {"dimensions": ["Uncaught Exception"], "metrics": [1, 10607]},
                    {"dimensions": ["Empty Page"], "metrics": [0.5, 10418]},
                ]
            }
        ),
        "errors.top_errors_by_error_name",
    )
    assert top_errors.status == "ok"
    assert top_errors.data["rows"][0]["error_sessions"] == 10607
    assert top_errors.data["rows"][0]["error_session_percent"] == 100

    error_percentage = parse_card(
        _parser_call(
            response_json={
                "rows": [
                    {"dimensions": ["operaciones con cheques"], "metrics": [1]},
                    {"dimensions": ["solicitar qr"], "metrics": [1]},
                    {"dimensions": ["agregar curp"], "metrics": [1]},
                ]
            }
        ),
        "errors.error_session_percentage_by_app_name",
    )
    assert error_percentage.status == "ok"
    assert [row["name"] for row in error_percentage.data["rows"]] == [
        "operaciones con cheques",
        "solicitar qr",
        "agregar curp",
    ]

    donut = parse_card(
        _parser_call(
            response_json={
                "rows": [
                    {"dimensions": ["portabilidad"], "metrics": [1847]},
                    {"dimensions": ["pagos"], "metrics": [703]},
                ]
            }
        ),
        "errors.error_sessions_by_app_name_comparison",
    )
    assert donut.status == "ok"
    assert donut.data["widget"]["total"] == 2550

    web_donut = parse_card(
        _parser_call(
            response_json={
                "rows": [
                    {"dimensions": [""], "metrics": [100]},
                    {"dimensions": ["a"], "metrics": [30]},
                    {"dimensions": ["b"], "metrics": [20]},
                    {"dimensions": ["c"], "metrics": [10]},
                    {"dimensions": ["d"], "metrics": [5]},
                    {"dimensions": ["e"], "metrics": [5]},
                ]
            }
        ),
        "errors.error_sessions_by_app_name_comparison",
    )
    assert web_donut.status == "ok"
    assert [item["name"] for item in web_donut.data["widget"]["series"]] == [
        "Null",
        "Other",
        "a",
        "b",
        "c",
    ]
    assert web_donut.data["widget"]["series"][0]["percent"] == 58.82

    historical = parse_card(
        _parser_call(
            response_json={"results": [[[], [[76.5, 88.9, 97.1]]]]},
        ),
        "summary.avg_session_duration",
    )
    assert historical.status == "ok"
    assert historical.data["widget"]["value"] == 76.5

    timeseries = parse_card(
        _parser_call(
            response_json={
                "rows": [
                    {"dimensions": [1781589600], "metrics": [10]},
                    {"dimensions": [1781593200], "metrics": [12]},
                ]
            }
        ),
        "summary.sessions",
    )
    assert timeseries.status == "ok"
    assert timeseries.data["widget"]["timeseries"] == [
        {"ts": "1781589600", "value": 10.0},
        {"ts": "1781593200", "value": 12.0},
    ]


def test_line_chart_payload_combines_devices_as_daily_visual_series() -> None:
    payload = build_line_chart_payload_from_series(
        role="summary.page_views",
        title="Paginas vistas",
        unit="count",
        mobile_points=[
            {"ts": "2026-06-23T07:00:00Z", "value": 10},
            {"ts": "2026-06-23T19:00:00Z", "value": 20},
            {"ts": "2026-06-24T07:00:00Z", "value": 30},
        ],
        desktop_points=[
            {"ts": "2026-06-23T07:00:00Z", "value": 1},
            {"ts": "2026-06-24T07:00:00Z", "value": 2},
        ],
        response_json={"metadata": {"timezone": "CST"}},
        aggregate_daily=True,
    )

    assert payload is not None
    assert payload["granularity"] == "daily"
    assert [series["label"] for series in payload["series"]] == ["Mobile", "Desktop"]
    assert [point["value"] for point in payload["series"][0]["points"]] == [30.0, 30.0]
    assert [point["value"] for point in payload["series"][1]["points"]] == [1.0, 2.0]
    assert all(len(series["points"]) <= 7 for series in payload["series"])

    seconds_payload = build_line_chart_payload_from_series(
        role="summary.avg_session_duration",
        title="Tiempo medio de sesion",
        unit="seconds",
        mobile_points=[],
        desktop_points=[
            {"ts": "2026-06-23T07:00:00Z", "value": 0},
            {"ts": "2026-06-23T08:00:00Z", "value": 120},
            {"ts": "2026-06-23T09:00:00Z", "value": 240},
        ],
        response_json={"metadata": {"timezone": "CST"}},
        aggregate_daily=True,
    )

    assert seconds_payload is not None
    assert seconds_payload["series"][1]["points"][0]["value"] == 180.0

    partial_payload = build_line_chart_payload_from_series(
        role="summary.page_views",
        title="Paginas vistas",
        unit="count",
        mobile_points=[
            {"ts": "2026-06-23T07:00:00Z", "value": 10},
            {"ts": "2026-06-28T07:00:00Z", "value": 20},
            {"ts": "2026-06-29T07:00:00Z", "value": 999},
        ],
        desktop_points=[],
        response_json={"metadata": {"timezone": "CST"}},
        aggregate_daily=True,
        period_end="2026-06-29T09:59:59Z",
    )

    assert partial_payload is not None
    assert [point["label"] for point in partial_payload["series"][0]["points"]] == [
        "Jun 23",
        "Jun 28",
    ]

    captured_payload = build_line_chart_payload_from_series(
        role="summary.page_views",
        title="Paginas vistas",
        unit="count",
        mobile_points=[
            {"ts": "2026-06-23T08:00:00Z", "value": 10},
            {"ts": "2026-06-23T07:00:00Z", "value": 5},
        ],
        desktop_points=[],
        response_json={"metadata": {"timezone": "CST"}},
    )

    assert captured_payload is not None
    assert captured_payload["granularity"] == "captured"
    assert [point["value"] for point in captured_payload["series"][0]["points"]] == [5.0, 10.0]


def _store_with_fixtures(tmp_path: Path) -> ParquetStore:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    store.merge_raw_calls("MX", _fixture_rows())
    return store


def _fixture_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for file_name in ("summary_raw_calls.json", "errors_raw_calls.json"):
        rows.extend(json.loads((FIXTURE_DIR / file_name).read_text()))
    return rows


def _real_call(
    *,
    tab: str,
    card_type: str,
    metric_ids: list[str] | None = None,
    dimension_path: list[str] | None = None,
) -> dict[str, Any]:
    metric_ids = metric_ids or []
    dimensions = [{"path": dimension_path, "metadata": {"title": "Name"}}] if dimension_path else []
    return {
        "tab": tab,
        "card_type": card_type,
        "metric_ids": json.dumps(metric_ids),
        "view_name": "table" if card_type == "TABLE" else "dimensionQuery",
        "request_json": json.dumps(
            {
                "query": {
                    "metadata": {
                        "cardType": card_type,
                        "metricIds": metric_ids,
                        "viewName": "table" if card_type == "TABLE" else "dimensionQuery",
                    },
                    "dimensions": {"dimensions": dimensions},
                }
            }
        ),
        "response_json": "{}",
    }


def _summary_metric_shape_call(
    path: list[str],
    *,
    aggregation: list[str] | None = None,
    filter_text: str | None = None,
) -> dict[str, Any]:
    metric_filter: dict[str, Any] = {"arguments": []}
    if filter_text:
        metric_filter = {
            "arguments": [
                {
                    "predicateFnNamespace": ["qm", "default", "predicates", "like"],
                    "arguments": [{"path": ["event", "value"]}, filter_text],
                }
            ]
        }
    return {
        "tab": "summary",
        "card_type": "CHART",
        "view_name": "timeSeriesQuery",
        "metric_ids": "[]",
        "request_json": json.dumps(
            {
                "metadata": {"cardType": "CHART", "viewName": "timeSeriesQuery"},
                "metrics": {
                    "metrics": [
                        {
                            "measures": [
                                {
                                    "aggregationFnNamespace": aggregation
                                    or ["qm", "default", "aggregations", "count"],
                                    "column": {"path": path},
                                    "filter": metric_filter,
                                }
                            ]
                        }
                    ]
                },
            }
        ),
        "response_json": "{}",
    }


def _parser_call(response_json: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_json": "{}",
        "response_json": json.dumps(response_json),
    }
