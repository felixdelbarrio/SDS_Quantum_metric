# CO/MX Last 7 Days Regression Plan

## Scope

- Colombia SDS manual dashboard.
- Mexico default dashboard.
- Range: `last_7_days`.
- Source of truth: Quantum Web.
- Local source: persisted raw, derived and regression datasets.

## Required Steps

1. Ensure controlled Quantum session is authenticated.
2. Run `Test pais` for CO and MX.
3. Run `Actualizar dashboards` for CO and MX.
4. Add or select Colombia SDS.
5. Validate dashboard structure.
6. Set the target dashboard as default.
7. Run `last_7_days` ingestion.
8. Run regression filtered by country, dashboard and range.
9. Verify every enabled and supported widget is `PASSED`.

## Current Execution Result

Blocked on 2026-07-07 because Quantum Web redirects the local controlled profile to authentication for both CO and MX. No truthful widget parity verdict can be issued until an authenticated session is available.

## Expected Evidence Files

- `docs/regression/iteration-15-co-sds-last-7-days.md`
- `docs/regression/iteration-15-co-sds-last-7-days.json`
- `docs/regression/iteration-15-mx-default-last-7-days.md`
- `docs/regression/iteration-15-mx-default-last-7-days.json`
