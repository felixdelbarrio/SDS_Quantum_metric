from datetime import UTC, datetime

from backend.app.ingestion.policy import apply_ingestion_range, build_ingestion_range
from backend.app.ingestion.service import _preset_range


def test_backfill_range_uses_maximum_window_when_no_local_data() -> None:
    now = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)

    ingestion_range = build_ingestion_range(None, now=now)

    assert ingestion_range.mode == "backfill"
    assert ingestion_range.start == datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
    assert ingestion_range.end == now
    assert ingestion_range.lookback_days == 30


def test_incremental_range_reprocesses_only_configured_recent_days() -> None:
    now = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)
    latest = datetime(2026, 6, 10, 8, 30, tzinfo=UTC)

    ingestion_range = build_ingestion_range(latest, now=now)

    assert ingestion_range.mode == "incremental"
    assert ingestion_range.start == datetime(2026, 6, 9, 8, 30, tzinfo=UTC)
    assert ingestion_range.end == now
    assert ingestion_range.lookback_days == 1


def test_ingestion_range_accepts_custom_depth_and_reprocess_days() -> None:
    now = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)
    latest = datetime(2026, 6, 10, 8, 30, tzinfo=UTC)

    backfill = build_ingestion_range(None, now=now, depth_days=30)
    incremental = build_ingestion_range(
        latest,
        now=now,
        depth_days=30,
        incremental_reprocess_days=2,
    )

    assert backfill.start == datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
    assert incremental.start == datetime(2026, 6, 8, 8, 30, tzinfo=UTC)


def test_relative_presets_use_quantum_web_complete_hour_cutoff() -> None:
    now = datetime(2026, 6, 29, 11, 20, tzinfo=UTC)

    today = _preset_range("today", now=now)
    last_7_days = _preset_range("last_7_days", now=now)

    assert today is not None
    assert today.start == datetime(2026, 6, 29, 6, 0, tzinfo=UTC)
    assert today.end == datetime(2026, 6, 29, 9, 59, 59, tzinfo=UTC)
    assert last_7_days is not None
    assert last_7_days.start == datetime(2026, 6, 23, 6, 0, tzinfo=UTC)
    assert last_7_days.end == datetime(2026, 6, 29, 9, 59, 59, tzinfo=UTC)


def test_today_preset_keeps_positive_window_early_in_cst_day() -> None:
    now = datetime(2026, 7, 10, 7, 38, tzinfo=UTC)

    today = _preset_range("today", now=now)

    assert today is not None
    assert today.start == datetime(2026, 7, 10, 6, 0, tzinfo=UTC)
    assert today.end == datetime(2026, 7, 10, 6, 59, 59, tzinfo=UTC)


def test_apply_ingestion_range_rewrites_nested_ts_preserving_timestamp_shape() -> None:
    ingestion_range = build_ingestion_range(
        datetime(2026, 6, 10, tzinfo=UTC),
        now=datetime(2026, 6, 13, tzinfo=UTC),
    )
    payload = {
        "query": {
            "metadata": {"cardId": "card"},
            "ts": ["2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z"],
        },
        "nested": [{"ts": [1_717_200_000_000, 1_717_286_400_000]}],
    }

    rewritten, changed = apply_ingestion_range(payload, ingestion_range)

    assert changed is True
    assert rewritten["query"]["ts"] == [
        "2026-06-09T00:00:00Z",
        "2026-06-13T00:00:00Z",
    ]
    expected_start_ms = round(datetime(2026, 6, 9, tzinfo=UTC).timestamp() * 1000)
    expected_end_ms = round(datetime(2026, 6, 13, tzinfo=UTC).timestamp() * 1000)
    assert rewritten["nested"][0]["ts"] == [expected_start_ms, expected_end_ms]
