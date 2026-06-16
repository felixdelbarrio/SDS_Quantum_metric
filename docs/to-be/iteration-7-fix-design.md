# Iteration 7 Fix Design

## Objective

Make the local app operationally strict: ingestion owns RAW capture, derived build, internal validation and Web vs Local regression. The user can ingest, inspect, import, export and delete, but cannot manually trigger maintenance steps.

## Key Decisions

- Datasets deletion is country-atomic through `ParquetStore.delete_country_all(country, confirm=country)`.
- Ingestion history is split into active jobs and historical jobs.
- Time range rewriting supports Quantum predicates where `arguments[0].path == ["session", "ts"]`.
- Local dashboard endpoints accept `range=today` and `range=last_7_days`, and still accept explicit dates.
- Derived rows carry `range_key`, `period_start`, `period_end`, `period_label` and `timezone`.
- Regression can be generated for separate report slugs: `today-web-vs-local` and `last-7-days-web-vs-local`.
- Required chart cards fail regression when `chart_payload` is missing or incomplete.
- Frontend Datasets no longer renders `Auditar`, `Regenerar derivados` or `Ejecutar regresion`.

## Non-Negotiables

- No mock values in product paths.
- No invented chart curves or empty Desktop series.
- No user-facing manual derived/regression/audit buttons.
- No `completed` ingestion state if strict regression reports fail.
