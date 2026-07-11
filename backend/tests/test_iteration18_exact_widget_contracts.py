from __future__ import annotations

import json
from pathlib import Path

from backend.app.config.settings import Settings
from backend.app.quantum.schemas import QuantumWidgetConfig
from backend.app.quantum_dashboard.builder import build_derived_datasets
from backend.app.quantum_dashboard.contracts import (
    DisplayNumberContract,
    QuantumChartContract,
    QuantumTableContract,
)
from backend.app.quantum_dashboard.correlation import correlate_call_to_widget
from backend.app.quantum_dashboard.generic_roles import dashboard_tab_for_widget
from backend.app.quantum_dashboard.parsers import (
    resolve_chart_contract,
    resolve_primary_value_from_contract,
    resolve_table_contract,
)
from backend.app.quantum_dashboard.regression import _table_row_signature
from backend.app.quantum_dashboard.visual_contracts import (
    _chart_contract,
    merge_visual_contracts,
    visual_contracts_are_complete,
)
from backend.app.quantum_dashboard.widget_roles import (
    descriptors_from_widgets,
    enrich_calls_with_live_contracts,
    resolve_call_role,
)
from backend.app.storage.parquet_store import ParquetStore


def test_display_contract_preserves_score_percent_and_precision() -> None:
    score = resolve_primary_value_from_contract(
        {"visual_contract": {"display": _display(9.3, "score", 1, "9.3")}}, {}
    )
    rate = resolve_primary_value_from_contract(
        {"visual_contract": {"display": _display(9.9, "percent", 2, "9.90%")}}, {}
    )
    task_success = resolve_primary_value_from_contract(
        {"visual_contract": {"display": _display(76.45, "percent", 2, "76.45%")}},
        {},
    )

    assert isinstance(score.value, DisplayNumberContract)
    assert isinstance(rate.value, DisplayNumberContract)
    assert isinstance(task_success.value, DisplayNumberContract)
    assert score.value.display_value == 9.3
    assert score.value.precision == 1
    assert rate.value.formatted == "9.90%"
    assert rate.value.precision == 2
    assert task_success.value.display_value == 76.45


def test_primary_value_never_sums_or_averages_timeseries_rows() -> None:
    resolution = resolve_primary_value_from_contract(
        {},
        {
            "rows": [
                {"dimensions": ["2026-07-01T00:00:00Z"], "metrics": [9.0]},
                {"dimensions": ["2026-07-01T01:00:00Z"], "metrics": [9.6]},
            ]
        },
    )

    assert resolution.status == "missing"
    assert resolution.value is None


def test_primary_value_applies_quantum_percent_scale_and_display_precision() -> None:
    resolution = resolve_primary_value_from_contract(
        {
            "visual_contract": {
                "unit": "percent",
                "scale": 100,
                "precision": 2,
                "suffix": "%",
                "formatted": "56.86%",
            }
        },
        {"rows": [{"dimensions": [], "metrics": [0.5686002123142]}]},
    )

    assert resolution.status == "resolved"
    assert isinstance(resolution.value, DisplayNumberContract)
    assert resolution.value.raw_value == 0.5686002123142
    assert resolution.value.display_value == 56.86002123142
    assert resolution.value.precision == 2
    assert resolution.value.formatted == "56.86%"


def test_chart_contract_preserves_bar_series_bands_legends_period_and_timezone() -> None:
    chart = {
        "chart_type": "bar",
        "x_axis": {"ticks": [{"value": "00:00", "label": "00:00"}]},
        "y_axis": {"ticks": [{"value": 0, "label": "0"}]},
        "series": [
            {
                "series_id": "sessions",
                "label": "Sessions",
                "kind": "bar",
                "order": 0,
                "points": [{"label": "00:00", "value": 12_005}],
            },
            {
                "series_id": "baseline",
                "label": "Historical baseline",
                "kind": "baseline",
                "order": 1,
                "points": [{"label": "00:00", "value": 11_900}],
            },
        ],
        "bands": [
            {
                "band_id": "anomaly-1",
                "label": "Anomaly",
                "kind": "anomaly",
                "start": "2026-07-01T00:00:00Z",
                "end": "2026-07-01T01:00:00Z",
                "start_x": 0.25,
                "end_x": 0.5,
                "pattern": "hatched",
            }
        ],
        "legends": [{"id": "sessions", "label": "Sessions", "kind": "bar", "order": 0}],
        "period_label": "Jul 01, 2026 (COT)",
        "timezone": "America/Bogota",
        "granularity": "hour",
    }

    resolution = resolve_chart_contract({"visual_contract": {"chart": chart}}, {})

    assert resolution.status == "resolved"
    assert isinstance(resolution.value, QuantumChartContract)
    assert resolution.value.chart_type == "bar"
    assert [series.kind for series in resolution.value.series] == ["bar", "baseline"]
    assert resolution.value.bands[0].pattern == "hatched"
    assert resolution.value.bands[0].start_x == 0.25
    assert resolution.value.bands[0].end_x == 0.5
    assert resolution.value.legends[0].label == "Sessions"
    assert resolution.value.period_label == "Jul 01, 2026 (COT)"
    assert resolution.value.timezone == "America/Bogota"


def test_chart_contract_populates_visible_series_from_quantum_timeseries() -> None:
    chart = {
        "chart_type": "line",
        "x_axis": {
            "ticks": [
                {"value": "Jul 09", "label": "Jul 09"},
                {"value": "Jul 10", "label": "Jul 10"},
            ]
        },
        "y_axis": {"unit": "percent", "ticks": []},
        "series": [
            {
                "series_id": "all-users",
                "label": "All Users",
                "kind": "line",
                "order": 0,
                "points": [],
            }
        ],
        "bands": [],
        "legends": [{"id": "all-users", "label": "All Users", "order": 0}],
        "period_label": "Last 7 Days (Jul 04 - 10, 2026)",
        "timezone": "America/Bogota",
        "granularity": "day",
    }
    response = {
        "rows": [
            {"dimensions": ["2026-07-09T05:00:00Z"], "metrics": [0.0287]},
            {"dimensions": ["2026-07-10T05:00:00Z"], "metrics": [0.0]},
        ]
    }

    resolution = resolve_chart_contract(
        {"visual_contract": {"scale": 100, "chart": chart}}, response
    )

    assert resolution.status == "resolved"
    assert isinstance(resolution.value, QuantumChartContract)
    assert [point.label for point in resolution.value.series[0].points] == [
        "Jul 09",
        "Jul 10",
    ]
    assert [point.value for point in resolution.value.series[0].points] == [2.87, 0.0]


def test_table_contract_preserves_exact_headers_and_default_sort() -> None:
    table = {
        "columns": [
            {"key": "error", "label": "Navigation Error", "data_type": "text"},
            {
                "key": "count",
                "label": "Occurrences",
                "data_type": "number",
                "sortable": True,
                "default_sort": "desc",
            },
        ],
        "default_sort_column": "count",
        "default_sort_direction": "desc",
        "period_label": "Jul 01, 2026 (COT)",
        "timezone": "America/Bogota",
    }
    rows = [{"error": "Possible Frustration", "count": 746}]

    resolution = resolve_table_contract({"visual_contract": {"table": table}}, {}, rows)

    assert resolution.status == "resolved"
    assert isinstance(resolution.value, QuantumTableContract)
    assert [column.label for column in resolution.value.columns] == [
        "Navigation Error",
        "Occurrences",
    ]
    assert resolution.value.default_sort_column == "count"
    assert resolution.value.rows == rows


def test_missing_tab_is_unassigned_and_never_inferred_from_title() -> None:
    resolution = dashboard_tab_for_widget(None, None, "Easy Dashboard")

    assert resolution.status == "unassigned"
    assert resolution.tab == "unassigned"
    assert resolution.evidence == ["missing_tab_contract"]


def test_duplicate_card_id_correlation_is_ambiguous() -> None:
    widgets = [
        QuantumWidgetConfig(
            role=f"generic.0.table.{name}",
            title=name,
            widget_id=f"widget-{name}",
            card_id="shared-card",
            widget_type="TABLE",
            enabled=True,
            supported=True,
        )
        for name in ("first", "second")
    ]

    resolution = correlate_call_to_widget(
        {"card_id": "shared-card", "request_json": {}, "response_json": {}},
        descriptors_from_widgets(widgets),
    )

    assert resolution.status == "ambiguous"
    assert resolution.error_code == "failed_ambiguous_widget_correlation"
    assert len(resolution.candidates) == 2


def test_duplicate_card_id_is_resolved_by_declared_quantum_selection() -> None:
    widgets = [
        QuantumWidgetConfig(
            role=f"generic.0.table.{name}",
            title=name,
            widget_id=f"widget-{name}",
            card_id="shared-card",
            widget_type="TABLE",
            visual_contract={
                "query": {
                    "metric_ids": ["sessions"],
                    "selection_tokens": selections,
                    "fingerprint": name,
                }
            },
            enabled=True,
            supported=True,
        )
        for name, selections in (
            ("technical", ["Long Running Spinner", "Datalayer Error"]),
            ("usability", ["Rage Click", "Possible Frustration"]),
        )
    ]
    call = {
        "card_id": "shared-card",
        "request_json": {
            "metrics": ["sessions"],
            "selections": ["Rage Click", "Possible Frustration"],
        },
    }

    role, descriptor = resolve_call_role(
        call,
        descriptors=descriptors_from_widgets(widgets),
    )

    assert role == "generic.0.table.usability"
    assert descriptor is not None
    assert descriptor.widget_id == "widget-usability"


def test_empty_table_reuses_only_schema_from_same_quantum_metric() -> None:
    widgets = [
        QuantumWidgetConfig(
            role=f"generic.0.table.{name}",
            title=name,
            widget_id=f"widget-{name}",
            card_id="shared-card",
            widget_type="TABLE",
            visual_contract={
                "query": {
                    "metric_ids": ["sessions-metric"],
                    "fingerprint": name,
                }
            },
            enabled=True,
            supported=True,
        )
        for name in ("technical", "usability")
    ]
    columns = [
        {"key": "name", "label": "Error Name", "data_type": "text"},
        {"key": "metric_1", "label": "Sessions (count)", "data_type": "number"},
    ]

    rows = enrich_calls_with_live_contracts(
        [{"widget_id": "widget-usability", "card_id": "shared-card"}],
        descriptors=descriptors_from_widgets(widgets),
        live_contracts={
            "widget-technical": {"table": {"columns": columns, "rows": [{"name": "Rage Click"}]}}
        },
    )

    table = rows[0]["visual_contract"]["table"]
    assert table["columns"] == columns
    assert table["rows"] == []


def test_explicit_role_attaches_live_contract_and_canonical_widget_identity() -> None:
    widget = QuantumWidgetConfig(
        role="summary.converted_sessions",
        title="Converted sessions",
        widget_id="converted-widget",
        card_id="shared-card",
        widget_type="CHART",
        visual_contract={"query": {"metric_ids": ["converted"]}},
        enabled=True,
        supported=True,
    )
    live_chart = {
        "chart_type": "line",
        "x_axis": {"ticks": []},
        "y_axis": {"ticks": []},
        "series": [],
        "bands": [],
        "legends": [],
        "period_label": "Last 7 Days",
        "timezone": "America/Mexico_City",
        "granularity": "day",
    }

    rows = enrich_calls_with_live_contracts(
        [{"card_role": "summary.converted_sessions", "widget_id": "shared-card"}],
        descriptors=descriptors_from_widgets([widget]),
        live_contracts={"converted-widget": {"chart": live_chart}},
    )

    assert rows[0]["widget_id"] == "converted-widget"
    assert rows[0]["visual_contract"]["chart"] == live_chart


def test_invalid_chart_build_preserves_last_coherent_range_snapshot(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    dataset = "range_key=last_7_days/derived/dashboard_widgets"
    store.write_country_dataset("CO", dataset, [{"id": "coherent-snapshot"}])
    role = "generic.1.chart.required"
    widget = QuantumWidgetConfig(
        role=role,
        title="Required chart",
        widget_id="required-widget",
        card_id="required-card",
        widget_type="CHART",
        tab="details",
        tab_name="Details",
        tab_index=1,
        layout_height=18,
        visual_contract={"query": {"metric_ids": ["required-metric"]}},
        enabled=True,
        required=True,
        supported=True,
    )
    raw_call = {
        "ingestion_id": "invalid-ingestion",
        "country": "CO",
        "dashboard_id": "sds-co",
        "widget_id": "required-widget",
        "card_id": "required-card",
        "card_role": role,
        "card_title": "Required chart",
        "card_type": "CHART",
        "view_name": "coreMetrics",
        "request_json": json.dumps({"metric": "required-metric"}),
        "response_json": json.dumps({"rows": [{"dimensions": [], "metrics": [7.5]}]}),
        "visual_contract": {
            "unit": "score",
            "scale": 1,
            "precision": 2,
            "formatted": "7.50",
        },
        "row_count": 1,
        "range_key": "last_7_days",
        "range_start": "2026-07-05T05:00:00Z",
        "range_end": "2026-07-11T14:59:59Z",
        "range_timezone": "America/Bogota",
        "source_ts_start": "2026-07-05T05:00:00Z",
        "source_ts_end": "2026-07-11T14:59:59Z",
        "query_hash": "query",
        "response_hash": "response",
    }

    build = build_derived_datasets(
        store,
        "CO",
        raw_calls=[raw_call],
        ingestion_id="invalid-ingestion",
        enabled_roles={role},
        dashboard_id="sds-co",
        range_key="last_7_days",
        widget_configs=[widget],
    )

    assert build.published is False
    assert build.regression_status == "failed_missing_chart_payload"
    assert store.read_country_dataset("CO", dataset) == [{"id": "coherent-snapshot"}]


def test_generic_table_signature_ignores_duplicate_and_formatted_fields() -> None:
    role = "generic.0.table.errors"
    web_row = {
        "dimension_1": "Long Running Spinner",
        "name": "Long Running Spinner",
        "metric_1": 2.0,
    }
    local_row = {
        "name": "Long Running Spinner",
        "name_formatted": "Long Running Spinner",
        "metric_1": 2.0,
        "metric_1_formatted": "2",
    }

    assert _table_row_signature(role, web_row) == _table_row_signature(role, local_row)


def test_visual_contract_merge_never_replaces_complete_chart_with_partial_sample() -> None:
    complete = {
        "chart": {
            "series": [
                {"kind": "line", "points": [{"value": 1}]},
                {"kind": "baseline", "points": [{"value": 2}]},
            ],
            "bands": [
                {
                    "kind": "historical_range",
                    "lower_points": [{"value": 0}],
                    "upper_points": [{"value": 3}],
                }
            ],
        }
    }
    partial = {
        "chart": {
            "series": [{"kind": "line", "points": [{"value": 1}]}],
            "bands": [{"kind": "historical_range"}],
        }
    }

    merged = merge_visual_contracts(complete, partial)

    assert len(merged["chart"]["series"]) == 2
    assert merged["chart"]["bands"][0]["lower_points"] == [{"value": 0}]
    assert visual_contracts_are_complete(
        {
            "widget": {
                **merged,
                "chart": {
                    **merged["chart"],
                    "legends": [
                        {"label": "All Users; Baseline"},
                        {"label": "Historical Range"},
                    ],
                },
            }
        }
    )


def test_dom_chart_contract_captures_baseline_band_and_bar_whiskers() -> None:
    line = _chart_contract(
        {
            "pivotHook": "multi-line-chart",
            "xTicks": ["Jul 10", "Jul 11"],
            "yTicks": ["0", "10"],
            "legends": ["All Users", "All Users; Baseline", "Historical Range"],
            "period": "Last 7 Days",
            "seriesData": [
                {
                    "id": "users",
                    "label": "All Users",
                    "values": [[1, 4], [2, 5]],
                    "dasharray": "1px, 5px",
                },
                {
                    "id": "users",
                    "label": "All Users",
                    "values": [[1, 6], [2, 7]],
                    "dasharray": "none",
                },
            ],
            "bandsData": [
                {"points": [{"x": 1, "low": 3, "high": 8}, {"x": 2, "low": 4, "high": 9}]}
            ],
            "highlightsData": [
                {"start": 1, "end": 2, "label": "Error", "startX": None, "endX": None}
            ],
        },
        {"unit": "count", "scale": 1},
        timezone="America/Bogota",
    )
    bars = _chart_contract(
        {
            "pivotHook": "stacked-bar-chart",
            "xTicks": ["Jul 10", "Jul 11"],
            "yTicks": ["0", "20"],
            "legends": ["All Users", "Historical Range"],
            "period": "Last 7 Days",
            "whiskersData": [{"low": 2, "high": 8}, {"low": 3, "high": 9}],
        },
        {"unit": "count", "scale": 1},
        timezone="America/Bogota",
    )

    assert line["series"][0]["kind"] == "line"
    assert line["series"][1]["kind"] == "baseline"
    assert len(line["bands"][0]["lower_points"]) == 2
    assert line["bands"][1]["start_x"] == 0
    assert line["bands"][1]["end_x"] == 1
    assert [point["value"] for point in bars["bands"][0]["upper_points"]] == [8, 9]


def _display(value: float, unit: str, precision: int, formatted: str) -> dict[str, object]:
    return {
        "raw_value": value,
        "display_value": value,
        "unit": unit,
        "scale": 1,
        "precision": precision,
        "formatted": formatted,
    }
