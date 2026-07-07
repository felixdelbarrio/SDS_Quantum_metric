# Iteration 15 Ingestion Failure RCA

Date: 2026-07-07

## Failure Modes Reviewed

| Area | Finding | Evidence | Current behavior |
|---|---|---|---|
| Navigation | Dashboard URL did not carry the selected preset range. | `dashboard_tab_url()` only included `tab` and `teamID`. | URL now includes `ts=<range_key>` when an ingestion range exists. |
| Session | Controlled profile can be unauthenticated. | Live audit redirected both MX and CO to authentication. | Ingestion preflight maps missing manual cookie to `failed_no_session`; browser auth still requires user session. |
| Dashboard default | Ingestion depended on a validated default dashboard. | `IngestionService._run()` checks `country_config.default_dashboard()`. | Missing or unvalidated dashboard maps to `failed_dashboard_not_found`. |
| Widgets | Empty enabled-widget set was generic failure. | `enabled_roles` raised `RuntimeError`. | Now maps to `failed_no_widgets`. |
| Analytics capture | Capture raised on first tab with no analytics responses. | `capture_quantum_dashboard_cards()` threw inside the tab loop. | It now tries all configured tabs and fails only if all are empty. |
| Endpoint listening | Capture listens to `/analytics` and `/analytics/historical`. | `QuantumAnalyticsCaptureSession._is_quantum_analytics()`. | Metadata GraphQL is handled by dashboard discovery, not raw analytics capture. |
| Timeout/cancel | Task cancellation was indistinguishable from user cancellation. | `CancelledError` set `cancelled`. | Explicit cancellation now reports `cancelled_by_user`. |

## Root Cause

The critical bug was not one single endpoint. It was a set of contract leaks:

- range state was implicit in the browser instead of explicit in the dashboard URL;
- no-response capture was treated as a tab-level fatal error;
- service-level statuses collapsed actionable failures into `failed`;
- the UI could not show the exact failure state.

## Fixed Status Contract

- `failed_no_session`
- `failed_dashboard_not_found`
- `failed_no_widgets`
- `failed_no_analytics_responses`
- `failed_regression`
- `cancelled_by_user`
- `completed`
- `completed_with_warnings`

## Remaining Live Validation Blocker

CO SDS and MX last 7 days ingestion cannot be truthfully marked `completed` in this environment because Quantum Web redirects to authentication for both domains. Once an authenticated controlled profile is available, rerun:

1. `Test pais`.
2. `Actualizar dashboards`.
3. `Validar dashboard`.
4. Ingest `last_7_days`.
5. Run regression for the selected dashboard.

## Diagnostics Required On Future Failures

Record:

- country;
- dashboard_id;
- dashboard name;
- team_id;
- source API/manual/cache;
- range_key;
- failing tab;
- endpoint current;
- first status;
- request/response hashes when available;
- first divergence stage.
