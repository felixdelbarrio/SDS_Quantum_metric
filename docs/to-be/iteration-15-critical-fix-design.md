# Iteration 15 Critical Fix Design

## Goals

- Treat Quantum Web `resourcesList` as the dashboard-list source of truth.
- Show every dashboard returned by the real API.
- Persist dashboard resources by country for offline selector use.
- Keep manual dashboards, including Colombia SDS, compatible with default selection and structure validation.
- Make ingestion failures actionable.

## Backend Changes

- `fetch_dashboard_resources_via_browser()` captures an authenticated `resourcesList` request, replays it through `POST https://api.quantummetric.com/query`, paginates by `totalCount`, and returns `DashboardResourcesResult`.
- `POST /api/quantum/countries/{country}/dashboards/refresh` now uses that resources result instead of summary rows.
- `GET /api/quantum/countries/{country}/dashboards` reads sanitized country cache before falling back to config.
- Cache path is tied to injected `Settings`, preventing wrong-directory reads in tests or alternate data dirs.
- `DashboardResourcesResult` accepts `dashboards` as an input alias and exposes `result.dashboards`.

## Frontend Changes

- Configuracion loads dashboard resources for the selected country.
- Selector options are the merge of config dashboards plus cached/API resources.
- Visible option label is `name`; internal value is `dashboard_id`.
- Selecting a cache-only option promotes it into the country config as default candidate.
- Action buttons expose pending, success and error states.

## Ingestion Changes

- Dashboard URLs include `ts=<range_key>`.
- Capture tries all configured tabs before declaring no analytics responses.
- Ingestion jobs distinguish missing session, missing dashboard, missing widgets, no analytics, regression failure and user cancellation.
- Derived availability is calculated from enabled/supported widget roles, not from a fixed historical set of datasets. This lets a completed CO SDS chunk publish its supported widget immediately.
- Chart contract validation stays strict for captured series. Aggregate chart widgets without Web-visible series compare by numeric Web/local parity.

## Acceptance Notes

Live validation on 2026-07-07 passed:

- CO SDS `last_7_days`: ingestion `9f17f495-f2d0-4c13-a3a4-beefb3dcfe89`, `1/1` enabled supported widgets, regression `PASSED`.
- MX Dashboard General MX `last_7_days`: ingestion `5c4d03fe-c72f-40ab-b2e7-507605fb6104`, `9/9` widgets, regression `PASSED`.

Reports are stored in `docs/regression/iteration-15-co-sds-last-7-days.*` and `docs/regression/iteration-15-mx-default-last-7-days.*`.
