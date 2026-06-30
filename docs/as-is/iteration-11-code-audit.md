# Iteration 11 Code Audit

Date: 2026-06-30
Branch: `feature/iteration-11-final-product-sanitization`
Evidence: `/Users/u517055/Downloads/Quantum Metrics - Iteracion 11.pdf`

## Scope Reviewed

Backend files reviewed:

- `backend/app/config/settings.py`
- `backend/app/quantum/config_store.py`
- `backend/app/ingestion/service.py`
- `backend/app/ingestion/planner.py`
- `backend/app/ingestion/policy.py`
- `backend/app/ingestion/time_rewriter.py`
- `backend/app/quantum_dashboard/service.py`
- `backend/app/quantum_dashboard/range_query.py`
- `backend/app/quantum_dashboard/builder.py`
- `backend/app/quantum_dashboard/parsers.py`
- `backend/app/quantum_dashboard/regression.py`
- `backend/app/quantum_dashboard/evidence.py`
- `backend/app/quantum_dashboard/chart_axes.py`
- `backend/app/quantum_dashboard/periods.py`
- `backend/app/quantum_dashboard/semantics.py`
- `backend/app/storage/parquet_store.py`
- `backend/app/api/routes.py`

Frontend files reviewed:

- `frontend/src/features/quantum-config/QuantumPage.tsx`
- `frontend/src/features/home/HomePage.tsx`
- `frontend/src/features/home/components/DashboardHeader.tsx`
- `frontend/src/features/home/components/KpiWidget.tsx`
- `frontend/src/features/home/components/CardExplorerModal.tsx`
- `frontend/src/features/home/components/SummaryDetailTable.tsx`
- `frontend/src/features/home/components/ErrorsTab.tsx`
- `frontend/src/features/home/components/charts/QuantumChart.tsx`
- `frontend/src/features/home/components/charts/QuantumBarChart.tsx`
- `frontend/src/features/home/components/charts/QuantumDonutChart.tsx`
- `frontend/src/features/datasets/DatasetsPage.tsx`
- `frontend/src/shared/design-system/tokens.css`
- `frontend/src/shared/design-system/global.css`
- `frontend/src/shared/api/client.ts`

Note: `frontend/src/features/home/components/charts/QuantumDonutChart.tsx` does not exist. Donut rendering currently lives in `QuantumChart.tsx`.

## PDF Findings Confirmed

The PDF has 12 pages. It documents these product issues with screenshots:

1. Configuration still says `Profundidad de ingesta` instead of `Profundidad por defecto`.
2. Dashboard exposes `Dashboard Dimension` and `Dashboard Segment`, but the local implementation is not a reliable product feature.
3. Chart detail `Barras` mode looks like line mode in local.
4. Summary table `Delta Page Views` and `Delta Sessions` are empty and lack color signaling.
5. `Detalle por App Name y Sistema operativo` appears expandable but expansion does not add trustworthy data.
6. `% Sesiones con Error por App Name` must match Quantum Web in order and content.
7. Switching to `Ayer` shows a red, non-actionable state and an inactive `Ingestar periodo`.
8. `Today` can lack an ingestion/update affordance.
9. Datasets can briefly show `Sin datos ingestados` while data is still loading.
10. Last 7 Days Web vs Local parity must be exact, including error-evolution decimals.

## Confirmed Code Findings

### 1. Dimension and Segment are exposed as product controls

`HomePage.tsx` imports and mounts `DimensionPicker` and `SegmentPicker`, fetches `/analytics/dimensions` and `/analytics/segments`, tracks local state, and passes `dimension` and `segment` into summary/errors queries.

`DashboardHeader.tsx` renders:

- chips `Dimension: sin dimension`
- chips `Segmento: sin segmento`
- buttons `Dimension`
- buttons `Segmento`

`backend/app/api/routes.py` still exposes `/analytics/dimensions` and `/analytics/segments`, and the local dashboard endpoints accept `dimension` and `segment` query params.

Conclusion: the controls are visible and partially wired, but they are not part of the strict captured Quantum Web contract requested for local. They should be removed from the local Dashboard surface. Backend internal segment helpers can only remain if not exposed as a false promise.

### 2. `Profundidad de ingesta` naming is still present

`QuantumPage.tsx` renders `Profundidad de ingesta`.

Docs also contain the old wording:

- `README.md`
- `ARCHITECTURE.md`
- `docs/runbooks/ingestion.md`
- older to-be docs

The persisted model field is `ingestion_depth_days`. The field name can remain internal to avoid schema churn, but UI/API descriptions/docs should call it `Profundidad por defecto` and explain that `/api/ingestions` uses it when no selected dashboard range is requested.

### 3. Default ingestion and selected-range ingestion are mixed in one endpoint

`IngestionService._run` supports:

- explicit `start_date` / `end_date`
- requested `days`
- preset `range_key`
- legacy depth-based backfill via `build_ingestion_range`

Current `IngestionCreate` defaults `range_key` to `last_7_days`. That means pressing the generic ingestion button can be interpreted as a range-contract ingestion rather than default-depth ingestion. This conflicts with the requested semantics:

- Ingestion page `Ingestar` must use configured default depth.
- Dashboard `Ingestar periodo` must ingest the selected range.

Conclusion: request models and frontend callers need clearer intent. A range-specific endpoint or reason field is needed to prevent ambiguous behavior.

### 4. Range coverage state exists but button enablement is too narrow

`range_query.py` produces `complete`, `partial`, `empty`, and warning levels. `DashboardHeader.tsx` only enables ingestion when `missing_days.length > 0`. If regression failed with local data but no missing days, the button can be disabled. If Today has no usable data, the UI may fail to expose a clear update action.

Conclusion: button enablement should use actionable range state, not only missing-day count.

### 5. Bar chart mode is a wrapper around line rendering

`QuantumBarChart.tsx` is only:

```tsx
return <QuantumChart {...props} />;
```

`CardExplorerModal.tsx` stores `view = "line" | "bar" | "table"`, but for both `line` and `bar` it renders `QuantumChart` with no chart-type override. Therefore `Barras` can render the same SVG path as line mode.

Conclusion: bar rendering must use real `rect` marks and exports must reflect the active chart view.

### 6. Summary table expansion is synthetic

`parsers.py` calls `_expandable_summary_rows(rows)` for summary detail rows. If Quantum does not provide hierarchy, the parser groups rows by app name and creates parent rows with:

- `is_expandable: True`
- synthetic `row_id`
- child rows only when an operating-system row differs from app name

This creates an expand affordance even when the captured Web table did not provide meaningful child rows.

Conclusion: remove synthetic expansion. Only preserve hierarchy when the Web/API response contains real child relationship fields and child count > 0.

### 7. Delta extraction exists but is incomplete/fragile

`parsers.py` extracts:

- `page_views_delta_percent`
- `sessions_delta_percent`
- `conversions_delta_percent`

But aliases are narrow, and `_expandable_summary_rows` can aggregate/replace rows and carry only first delta values. `SummaryDetailTable.tsx` renders deltas through an internal `MetricDelta`, but page views and sessions are frequently `null` in local data.

Conclusion: parser aliases and regression should explicitly fail when Web exposes a delta and Local loses it. Frontend should reuse the shared semantic component and show `-` only when the value is truly absent.

### 8. `% Sesiones con Error por App Name` is now mostly fixed but still needs strict contract

Current branch includes the prior fix from PR #30:

- default API sort is `row_index` asc
- frontend table default sort is `row_index`
- regression compares first visible row signatures

Remaining requirement: persist explicit `rank` / `web_order` / source hashes and keep regression strict for content, order, top N and percentage formatting.

### 9. Datasets false-empty state is present

`DatasetsPage.tsx` renders `Sin datos ingestados` whenever `rows.length` is false, without checking `datasets.isLoading` or `datasets.isFetching`. This matches the PDF issue: initial load can display false empty.

Conclusion: split states into loading, loaded_empty, loaded_with_data, and error. Entity area should also avoid showing empty states while entity queries are loading.

### 10. Performance risks

The dashboard service reads range-scoped derived datasets, which is good. Remaining risks:

- Datasets reads entity lists and first 100 rows without explicit loading-state separation in the UI.
- Dimension/Segment queries are extra dashboard work for controls that will be removed.
- Synthetic expansion duplicates summary rows and renders extra table state.
- Bar mode currently mounts the full line chart path even when bars are requested.

## Required Implementation Direction

1. Remove Dimension/Segment UI and dead frontend components/tests for Dashboard.
2. Keep local dashboard APIs range-scoped and stop passing dimension/segment from local UI.
3. Rename visible `Profundidad de ingesta` wording to `Profundidad por defecto` and document semantics.
4. Separate default-depth ingestion from selected-range ingestion.
5. Add real bar chart rendering with `rect` marks and active-view export.
6. Remove synthetic summary expansion and chevrons when no real children exist.
7. Strengthen delta parsing/rendering/regression.
8. Make range ingestion buttons active for missing, partial, empty and regression_failed states unless a matching ingestion is active.
9. Fix Datasets loading/empty states.
10. Regenerate Today, Yesterday and Last 7 Days regression reports after implementation.

