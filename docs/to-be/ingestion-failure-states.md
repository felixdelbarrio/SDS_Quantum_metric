# Ingestion Failure States

Iteration 16 keeps ingestion states actionable:

- `completed`: all enabled/supported widgets captured and regression passed.
- `completed_with_warnings`: capture finished but optional warnings remain.
- `failed_no_session`: no authenticated Quantum session.
- `failed_dashboard_not_found`: missing or unvalidated default dashboard.
- `failed_no_widgets`: no enabled supported widgets.
- `failed_no_analytics_responses`: no valid analytics responses for configured tabs.
- `failed_regression`: derived data exists but Web vs Local failed.
- `cancelled_by_user`: explicit user cancellation.

Implementation details:

- false cancellation is avoided; only `cancel()` sets `cancelled_by_user`;
- TABLE queries that Quantum already scopes with `ts=<range_key>` preserve their native range when forced rewriting breaks them;
- non-widget telemetry is captured as RAW evidence but excluded from widget derivation.
