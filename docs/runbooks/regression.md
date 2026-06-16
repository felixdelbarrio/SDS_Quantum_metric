# Regression Runbook

## Automatic Execution

Regression runs automatically after ingestion. The user should not trigger it from Datasets.

The required reports are:

- `docs/regression/today-web-vs-local.md`
- `docs/regression/today-web-vs-local.json`
- `docs/regression/last-7-days-web-vs-local.md`
- `docs/regression/last-7-days-web-vs-local.json`

## Developer CLI

For local diagnosis:

```bash
. .venv/bin/activate
python -m backend.app.quantum_dashboard.regression --country MX
```

## Failure Conditions

Regression fails if a mandatory card is missing, a derived dataset is missing, a chart card has no `chart_payload`, period labels are missing, axes/legends/series are incomplete, values differ outside tolerance, or table structure differs.

`failed_regression` means at least one required range report failed and ingestion must not be accepted as complete.
