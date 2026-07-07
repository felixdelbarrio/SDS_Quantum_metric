# Iteration 15 Critical RCA

Date: 2026-07-07

## Symptoms

- The dashboard selector could show one configured dashboard even when Quantum `resourcesList` returns multiple dashboards.
- The visible dashboard name could degrade to a generated fallback or a legacy ID-like value.
- Colombia actions looked inert because the UI had no per-action pending, success or error feedback and because a newly selected country existed only in the unsaved form state.
- Manual Colombia SDS required a full URL flow, but the parser contract did not expose the requested `parse_dashboard_url_or_id` entry point.
- Ingestion could finish as generic `failed` or `cancelled`, hiding the first actionable failure.
- Capture aborted on the first empty tab, so a valid second-tab analytics response could be missed.

## Root Causes

| Symptom | Root cause | Evidence | Fix |
|---|---|---|---|
| Combo with one element | The config page rendered `countries[].dashboards` and did not load the country dashboard resources cache on page load. | `QuantumPage.tsx` selected options from `selectedCountry.dashboards` only. | The page now queries `GET /api/quantum/countries/{country}/dashboards` and merges cached/API resources into the selector. |
| Combo not using real API contract | `POST /dashboards/refresh` degraded browser discovery into summaries, losing the `DashboardResourcesResult` contract and `total_count`. | `routes.py` converted `discover_dashboards_via_browser()` summaries through `result_from_resource_rows()`. | Added `fetch_dashboard_resources_via_browser()` and route refresh now persists the real `resourcesList` result. |
| `name` looks like ID/fallback | Legacy migration cleared only known generated names, while UI had no cache label source separate from config. | Existing code had `_is_legacy_generated_dashboard_name`; the selector still depended on config. | UI labels use `resource.name`/`dashboard.name`, never `dashboard_id`; model accepts `dashboards` alias. |
| Colombia buttons look inert | Mutations refetched config but had no inline pending/success/error state. | `testCountry`, `refreshDashboards`, `loadDashboardStructure` had handlers but no feedback. | Added `ActionFeedback`, `aria-busy`, and action-specific labels. |
| Colombia actions fail before save | The UI can add CO locally, but `Test pais`/`Actualizar dashboards`/`Validar dashboard` called backend endpoints that only read persisted config; saving was blocked until a default dashboard existed. | A new CO form row was not present in `QuantumConfigStore.read()`, so `required_country_config("CO")` raised before any Quantum call. | Country actions now accept `base_url` from the form, materialize the country draft server-side, and keep the final Save guard for validated defaults. |
| Manual dashboard validation gap | URL parser accepted URLs, while the requested contract includes URL or raw ID. | `manual_dashboard.py` exposed `parse_dashboard_url`; raw ID was handled indirectly in request merge. | Added `parse_dashboard_url_or_id()` and kept request flow compatible. |
| Ingestions failed/cancelled generically | `IngestionService` collapsed preflight and capture failures into `failed`; cancellation used `cancelled` for all task cancellations. | `except Exception` set `job.status = "failed"`; `CancelledError` set `"cancelled"`. | Added actionable statuses: `failed_no_session`, `failed_dashboard_not_found`, `failed_no_widgets`, `failed_no_analytics_responses`, `cancelled_by_user`. |
| Widgets mixed or lost by tab | Capture and progress assumed fixed `summary/errors` tabs and aborted on first empty tab. | `capture_quantum_dashboard_cards()` raised immediately per tab. | Capture includes `ts=<range>` and fails only when all configured tabs have no analytics responses. |
| Completed CO SDS chunk still showed empty dashboard | Local dashboard readiness required all historical derived datasets (`summary_table`, `errors_*`, `chart_payloads`) even when the configured dashboard enabled only `summary.sessions`. | CO SDS ingestion produced `summary_widgets` and regression `PASSED`, but `/api/local-dashboard/summary` returned `empty`. | Readiness now derives required datasets from enabled widget roles, so partial supported dashboards publish as soon as their enabled widgets pass regression. |
| CO SDS aggregate widget failed chart contract | `summary.sessions` is catalogued as a chart role, but SDS returned an aggregate value without visible series. Regression required `chart_payload` before attempting numeric parity. | Real CO SDS `last_7_days` captured value `6504.0` with empty timeseries and failed `failed_chart_contract_incomplete`. | Chart payload remains mandatory when Web/local series exist; aggregate widgets without visible series compare by Web/local value. |

## Quantum Dashboard List API

Quantum Web source of truth remains:

`POST https://api.quantummetric.com/query`

Operation: `resourcesList`.

Fields consumed: `totalCount`, `resources[].id`, `resources[].type`, `resources[].name`, `resources[].starred`.

The attached Iteration 15 PDF contains a real Colombia response with `totalCount=14` and dashboards including `Page Analysis` and `Dashboard General CO`.

## Local Dashboard List Implementation Gap

Before this iteration, the refresh route did call Web discovery, but it returned `QuantumDashboardSummary` rows. That summary path was enough to populate config in happy paths, but it was not the durable `DashboardResourcesResult` contract and did not make page-load cache the selector's first-class source.

The local selector now reads cache through `GET /api/quantum/countries/{country}/dashboards`. Refresh is explicit and writes sanitized cache to `config/dashboard_resources/<country>.json` under the injected settings directory.

## Colombia Button Failures

The buttons had click handlers, but the user-visible result was ambiguous because failures and success were only reflected after a config refetch. A second defect blocked new countries: CO was selectable in the unsaved form, while the endpoints only read stored config. The updated page exposes pending, success and error text for:

- `Test pais`.
- `Actualizar dashboards`.
- `Validar dashboard`.
- Manual dashboard validation.

The backend action endpoints also accept a sanitized draft payload with `base_url`, persist the country draft, and then execute the requested Quantum action. This lets users test and refresh Colombia before a default dashboard exists, while the main save action still refuses incomplete enabled countries.

## Manual Dashboard Validation Failure

Colombia SDS is supported as URL or raw ID:

- dashboard_id: `fccfa9f6-5d01-47cf-9ba6-b7bccd4d4f2b`
- team_id: `24feba5b-307d-40ed-83de-478111f8938e`
- name: `SDS`

The manual route still validates structure through Quantum Web and persists it as source `manual`.

## Ingestion Cancelled/Failed RCA

The generic message `No Quantum analytics responses were captured` had two separate causes:

- real zero analytics responses for the selected session/dashboard/range;
- false early abort when the first configured tab did not emit responses but another tab could.

The capture layer now collects all configured tabs before failing. The service maps no-response failures to `failed_no_analytics_responses` and reserves `cancelled_by_user` for explicit user cancellation.

## Widgets Grouping RCA

Structure discovery already parses `LoadDashboard -> entity.tabs -> layoutCardsMap` and tests prove `Resumen` and `Errores` separation for the fixture. The remaining risk was the UI selector/cache path and ingestion capture assuming fixed tabs. The UI groups by real `tab_id`, `tab_name`, or `tab_index`, with unassigned widgets under `Sin pestana`.

## Quantum Web Audit Result

On 2026-07-07, the controlled Chrome cookie provider loaded authenticated Quantum cookies for:

- `https://bbvamx.quantummetric.com`
- `https://bbvaco.quantummetric.com`

`POST https://api.quantummetric.com/query` returned authenticated permissions for both countries, and `resourcesList` returned:

- CO: `14` dashboards from Quantum GraphQL.
- MX: `18` dashboards from Quantum GraphQL.

Live `last_7_days` ingestions then completed:

- CO SDS: ingestion `9f17f495-f2d0-4c13-a3a4-beefb3dcfe89`, `45` calls, `565` rows, `1/1` enabled supported cards, regression `PASSED`.
- MX Dashboard General MX: ingestion `5c4d03fe-c72f-40ab-b2e7-507605fb6104`, `79` calls, `151` rows, `9/9` cards, regression `PASSED`.

Evidence is stored under `docs/regression/iteration-15-*-last-7-days.*`.

## Code To Delete

Deleted in this iteration:

- Route conversion helpers that reduced GraphQL resources to dashboard summaries.
- Unused route merge path for discovered summary dashboards.

No additional fixed-tab cleanup was required for the validated CO/MX dashboards. Capture still groups by configured tab metadata and skips unsupported widgets instead of inventing local data.

## Implementation Plan

1. Use `fetch_dashboard_resources_via_browser()` for route refresh.
2. Persist dashboard resources cache under injected settings.
3. Load dashboard resources in Configuracion per selected country.
4. Keep `dashboard_id` as value and `name` as visible label.
5. Accept manual dashboard URL or raw ID.
6. Add action feedback for all country/dashboard buttons.
7. Harden ingestion statuses and no-analytics handling.
8. Re-run focused backend/frontend tests, then full CI/build.
