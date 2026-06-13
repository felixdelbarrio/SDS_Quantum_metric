from datetime import UTC, datetime

from backend.app.ingestion.policy import apply_ingestion_range, build_ingestion_range


def test_backfill_range_uses_maximum_window_when_no_local_data() -> None:
    now = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)

    ingestion_range = build_ingestion_range(None, now=now)

    assert ingestion_range.mode == "backfill"
    assert ingestion_range.start == datetime(1970, 1, 1, tzinfo=UTC)
    assert ingestion_range.end == now


def test_incremental_range_uses_one_week_lookback_from_latest_source_date() -> None:
    now = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)
    latest = datetime(2026, 6, 10, 8, 30, tzinfo=UTC)

    ingestion_range = build_ingestion_range(latest, now=now)

    assert ingestion_range.mode == "incremental"
    assert ingestion_range.start == datetime(2026, 6, 3, 8, 30, tzinfo=UTC)
    assert ingestion_range.end == now


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
        "2026-06-03T00:00:00Z",
        "2026-06-13T00:00:00Z",
    ]
    expected_start_ms = round(datetime(2026, 6, 3, tzinfo=UTC).timestamp() * 1000)
    expected_end_ms = round(datetime(2026, 6, 13, tzinfo=UTC).timestamp() * 1000)
    assert rewritten["nested"][0]["ts"] == [expected_start_ms, expected_end_ms]
