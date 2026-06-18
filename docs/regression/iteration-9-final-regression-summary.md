# Iteration 9 Final Regression Summary

## Verdict

PASSED

## Scope

- Today.
- Yesterday.
- Last 7 Days.
- Widgets enabled in configuration.
- Local visualization from Parquet-derived datasets only.

## Evidence

- `docs/regression/today-web-vs-local.md`
- `docs/regression/yesterday-web-vs-local.md`
- `docs/regression/last-7-days-web-vs-local.md`
- `GET /api/datasets/MX/evidence`

## Notes

The regression compares captured Quantum Web snapshots against local derived Parquet. A fresh Quantum session is still required whenever the upstream Web dashboard changes or a manual dashboard is added.
