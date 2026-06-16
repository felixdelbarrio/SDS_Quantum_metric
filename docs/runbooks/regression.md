# Regression Runbook

Run the local regression command:

```bash
. .venv/bin/activate
python -m backend.app.quantum_dashboard.regression --country MX --dashboard general
```

Outputs:

- `docs/regression/latest-web-vs-local.md`
- `docs/regression/latest-web-vs-local.json`
- `data/parquet/country=MX/regression/web_vs_local_results/`
- `data/parquet/country=MX/regression/discrepancies/`

Verdicts:

- `PASSED`: all mandatory card values match exactly.
- `PASSED_WITH_TOLERANCE`: decimal or percentage differences are within `QUANTUM_REGRESSION_TOLERANCE_PERCENT`.
- `FAILED`: a mandatory card, API response, parser result, table, chart or value comparison failed.

CI uses sanitized fixtures under `backend/tests/fixtures/quantum_dashboard/`. GitHub Actions must not call Quantum Web or require real cookies.

For a real acceptance run, first authenticate in the configured browser, run ingestion for MX, then rerun regression and inspect the Markdown report before opening or marking a PR ready.
