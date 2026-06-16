# Iteration 7 Code Audit

## Scope

Reviewed the Iteration 7 request, `Quantum Metrics - Iteracion 7.pdf`, and the current `develop` branch before code changes.

Critical files reviewed:

- Backend ingestion: `backend/app/ingestion/service.py`, `capture.py`, `planner.py`, `policy.py`, `time_rewriter.py`
- Quantum dashboard: `backend/app/quantum_dashboard/capture.py`, `builder.py`, `parsers.py`, `regression.py`, `service.py`, `card_mapper.py`, `catalog.py`
- Storage/API: `backend/app/storage/parquet_store.py`, `backend/app/analytics/service.py`, `backend/app/api/routes.py`
- Frontend: Home, ingestion, datasets, chart components, design tokens and globals
- Build/security: `package.json`, `frontend/package.json`, `Makefile`

## Confirmed Findings

1. **Dataset delete is incomplete.** `DELETE /api/datasets/{country}` only calls `ParquetStore.delete_country`, which removes `data/parquet/country=*`. It does not remove country ingestion history from `data/manifests/ingestion_manifest.parquet`, runtime/cache files, regression docs, or exports.

2. **Ingestion history response is confusing.** `GET /api/ingestions` returns `{ active: [all in-memory jobs], persisted: [...] }`. Completed in-memory jobs remain under `active`, persisted jobs are separate, and chunk details are not modeled as a chronological list. The frontend concatenates both lists, so current and historical processes are visually mixed.

3. **Forbidden manual actions are visible.** `DatasetsPage.tsx` renders `Auditar`, `Regenerar derivados`, and `Ejecutar regresion`, directly contradicting the Iteration 7 requirement that derived build, audit, and regression are system actions.

4. **Automatic pipeline exists but is not strict enough.** `IngestionService._run` already captures RAW, builds derived datasets, and runs regression. However, it only runs one generic regression report and may allow `completed_with_warnings` when mandatory graphic evidence is missing. Iteration 7 requires strict Today and last-7-days reports and `failed_regression` on either failure.

5. **Chart payload failures are real, not just copy.** `build_derived_datasets` validates required chart payloads, but when validation fails it skips writing derived datasets. This leaves Home without usable chart payloads and Datasets without enough audit evidence to inspect partial parser output.

6. **The parser may expose misleading series.** `_line_chart_payload` always creates Mobile and Desktop legends/series, even when no Desktop points were captured. This can create false confidence and conflicts with the "no invented Desktop" rule.

7. **Time rewriter misses the real Quantum predicate shape.** `time_rewriter.py` expects `path` on the same object as `predicateFnNamespace`. The PDF/request shows Quantum commonly stores the field path in `arguments[0].path`, so nested `gte`/`lt` predicates can remain unmodified and extraction can produce wrong ranges.

8. **Range filtering is date-overlap based, not range-key based.** Local dashboard endpoints accept `start_date`/`end_date`, but not `range=today` / `range=last_7_days`, and derived rows do not consistently carry `range_key`, `period_start`, `period_end`, `period_label`, and `timezone`.

9. **Period labels are incomplete.** Widgets and chart payloads carry period labels, but labels are reduced to dates such as `Jun 16, 2026 (CST)` in some paths. The acceptance criteria require visible start time, end time, and timezone.

10. **Regression reports are not split by acceptance range.** `run_regression` writes `docs/regression/latest-web-vs-local.*` only. Iteration 7 requires `today-web-vs-local.*` and `last-7-days-web-vs-local.*`, each ending in `PASSED` or `FAILED`.

11. **Home status can guide users toward forbidden maintenance actions.** The local dashboard readiness reason and `QuantumChart` empty state tell users to regenerate derivatives or run regression. Those actions should happen automatically.

12. **Datasets entity console mostly exists.** `/api/datasets/{country}/entities`, schema, rows, export, import, and lazy pagination are present. The main gap is making the page the audit console by default without exposing manual maintenance buttons, plus adding delete semantics.

13. **Security audit fails with 4 high npm vulnerabilities.** `npm audit --json` reports high vulnerabilities through `vite`, `@vitejs/plugin-react`, `esbuild`, and `form-data`.

14. **CI does not enforce npm audit.** `make CI` runs frontend build/tests but does not run `npm audit --audit-level=high`.

## Root Cause Summary

- The app has Iteration 6 hardening primitives but still exposes maintenance operations as user actions.
- The ingestion pipeline runs derived/regression after capture, but its regression model is generic and does not encode the two required acceptance ranges.
- Time range rewriting/extraction is too narrow for real Quantum payload shape, so captured RAW can represent a different period than the UI selection.
- Chart payload derivation is all-or-nothing and does not persist enough partial evidence for Datasets inspection when validation fails.
- UI status copy and controls still reflect an operator workflow instead of an automatic product workflow.

## Change Direction

1. Add transactional country deletion that removes Parquet, ingestion history, runtime/cache, and country-scoped regression artifacts.
2. Return ingestions as `active` plus chronological `history`, with explicit `is_active`, `sort_index`, and chunk metadata.
3. Remove visible manual maintenance actions from Datasets.
4. Fix nested Quantum time predicate rewriting/extraction and persist range metadata.
5. Make derived rows range-aware and keep period labels with start/end/timezone.
6. Generate Today and last-7-days regression reports from the same strict engine and block completion on failure.
7. Update npm tooling/lockfile to remove high vulnerabilities and add audit to `make CI`.
