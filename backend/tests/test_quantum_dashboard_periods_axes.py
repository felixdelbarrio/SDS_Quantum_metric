from __future__ import annotations

from datetime import UTC, datetime

from backend.app.quantum_dashboard.chart_axes import readable_x_ticks
from backend.app.quantum_dashboard.periods import format_period_label, zoneinfo_for


def _utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    local = datetime(year, month, day, hour, minute, tzinfo=zoneinfo_for("CST"))
    return local.astimezone(UTC)


def test_today_period_label_is_quantum_web_readable() -> None:
    label = format_period_label(
        _utc(2026, 6, 18, 0),
        _utc(2026, 6, 18, 2, 59),
        "CST",
        preset="today",
    )

    assert label == "Today (Jun 18, 2026, 12:00am - 2:59am CST)"
    assert "178" not in label


def test_yesterday_period_label_is_quantum_web_readable() -> None:
    label = format_period_label(
        _utc(2026, 6, 17, 0),
        _utc(2026, 6, 17, 23, 59),
        "America/Mexico_City",
        preset="yesterday",
    )

    assert label == "Yesterday (Jun 17, 2026, 12:00am - 11:59pm CST)"
    assert "epoch" not in label.lower()


def test_last_7_days_period_label_is_readable() -> None:
    label = format_period_label(
        _utc(2026, 6, 12, 0),
        _utc(2026, 6, 18, 23, 59),
        "CST",
        preset="last_7_days",
    )

    assert label == "Jun 12, 2026 - Jun 18, 2026 (CST)"


def test_custom_period_label_is_readable() -> None:
    label = format_period_label(
        _utc(2026, 7, 1, 8, 15),
        _utc(2026, 7, 3, 18, 30),
        "CST",
        preset="custom",
    )

    assert label == "Jul 01, 2026 - Jul 03, 2026 (CST)"


def test_readable_x_ticks_limit_labels_and_hide_epoch() -> None:
    points = [
        {"ts": int(datetime(2026, 6, 18, hour, tzinfo=UTC).timestamp()), "value": hour}
        for hour in range(24)
    ]

    ticks = readable_x_ticks(points, preset="today")

    assert 1 <= len(ticks) <= 7
    assert all(not tick["label"].isdigit() for tick in ticks)
    assert {tick["label"] for tick in ticks} >= {"18:00"}
