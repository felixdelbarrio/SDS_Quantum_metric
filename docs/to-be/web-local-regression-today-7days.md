# Web vs Local Regression: Today and Last 7 Days

## Reports

The regression runner supports named range reports:

- `docs/regression/today-web-vs-local.md`
- `docs/regression/today-web-vs-local.json`
- `docs/regression/last-7-days-web-vs-local.md`
- `docs/regression/last-7-days-web-vs-local.json`

Each report ends with `PASSED` or `FAILED`.

## Comparison Scope

Mandatory cards are compared widget by widget:

- Summary KPIs and detail table.
- Error evolution, top errors, app comparison and app percentage table.
- Values, period labels, axis ticks, legends, series shape and table rows.

## Blocking Rule

Ingestion runs both reports automatically. If either report returns `FAILED`, the ingestion status becomes `failed_regression`.

## CI Fixtures

CI can exercise this contract with sanitized Parquet fixtures. Live Quantum Web parity still requires a configured browser session and cannot be truthfully asserted in offline CI.
