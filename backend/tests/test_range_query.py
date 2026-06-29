from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from backend.app.config.settings import Settings
from backend.app.quantum_dashboard.range_query import resolve_range
from backend.app.storage.parquet_store import ParquetStore


def test_today_partial_coverage_is_info_not_warning(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    _write_day(store, "2026-06-18")

    resolution = resolve_range(
        store,
        "MX",
        range_key="today",
        start="2026-06-18",
        end="2026-06-18",
        now=datetime(2026, 6, 18, 12, tzinfo=UTC),
    )

    assert resolution.completeness == "complete"
    assert resolution.warning_level == "none"


def test_yesterday_missing_day_is_warning(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))

    resolution = resolve_range(
        store,
        "MX",
        range_key="yesterday",
        start="2026-06-17",
        end="2026-06-17",
        now=datetime(2026, 6, 18, 12, tzinfo=UTC),
    )

    assert resolution.completeness == "empty"
    assert resolution.warning_level == "warning"
    assert resolution.missing_days[0].isoformat() == "2026-06-17"


def test_presets_without_explicit_dates_resolve_their_expected_days(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    now = datetime(2026, 6, 18, 12, tzinfo=UTC)

    today = resolve_range(store, "MX", range_key="today", start=None, end=None, now=now)
    yesterday = resolve_range(store, "MX", range_key="yesterday", start=None, end=None, now=now)
    last_7_days = resolve_range(store, "MX", range_key="last_7_days", start=None, end=None, now=now)

    assert [day.isoformat() for day in today.required_days] == ["2026-06-18"]
    assert [day.isoformat() for day in yesterday.required_days] == ["2026-06-17"]
    assert [day.isoformat() for day in last_7_days.required_days] == [
        "2026-06-12",
        "2026-06-13",
        "2026-06-14",
        "2026-06-15",
        "2026-06-16",
        "2026-06-17",
        "2026-06-18",
    ]


def test_passed_regression_marks_contract_range_coverage_complete(tmp_path: Path) -> None:
    store = ParquetStore(Settings(qm_data_dir=tmp_path))
    _write_day(store, "2026-06-12")

    resolution = resolve_range(
        store,
        "MX",
        range_key="last_7_days",
        start=None,
        end=None,
        now=datetime(2026, 6, 18, 12, tzinfo=UTC),
        last_regression_status="passed",
    )

    assert resolution.completeness == "complete"
    assert resolution.warning_level == "none"
    assert len(resolution.covered_days) == 7
    assert resolution.missing_days == []


def _write_day(store: ParquetStore, day: str) -> None:
    store.merge_raw_calls(
        "MX",
        [
            {
                "ingestion_id": f"ing-{day}",
                "country": "MX",
                "source_endpoint": "/analytics",
                "dashboard_id": "dash",
                "card_id": "card",
                "card_type": "LINE",
                "view_name": "line",
                "metric_ids": "[]",
                "query_hash": f"q-{day}",
                "response_hash": f"r-{day}",
                "row_count": 1,
                "source_ts_start": f"{day}T06:00:00Z",
                "source_ts_end": f"{day}T18:00:00Z",
            }
        ],
    )
