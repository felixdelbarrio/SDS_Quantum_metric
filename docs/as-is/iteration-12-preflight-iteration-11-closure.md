# Iteration 12 Preflight - Iteration 11 Closure

## Scope

Checked current `develop` after merge `ee05738` / PR #31.

## Findings

1. `Profundidad por defecto` is present in `frontend/src/features/quantum-config/QuantumPage.tsx`.
2. Dashboard Dimension and Dashboard Segment controls are absent from Home.
3. `DimensionPicker.tsx` and `SegmentPicker.tsx` are removed.
4. `/api/analytics/dimensions` and `/api/analytics/segments` are not exposed as API routes; tests assert 404.
5. Chart bar mode renders `rect.quantum-chart-bar`; tests assert no line path in bar mode.
6. Line mode still renders smooth SVG paths.
7. Table mode in the chart modal remains available through `CardExplorerModal`.
8. CSV/SVG/PNG export actions remain mounted in `QuantumChart`.
9. Summary parser extracts `Delta Page Views`, `Delta Sessions` and conversion deltas when Web/API returns them.
10. Delta semantic classes are rendered from tokens via `semantic-*`.
11. Parser no longer fabricates hierarchy when Web has no child rows.
12. Local dashboard service also normalizes older Parquet rows so stale `is_expandable=true` without children is not exposed.
13. `% Sesiones con Error por App Name` defaults to `row_index` ascending in `ErrorsTab` and `LocalDashboardService`.
14. Home uses `/api/ingestions/range` for selected period ingestion.
15. Today shows `Actualizar hoy` when coverage is actionable.
16. Datasets renders `Cargando datasets` during initial load and only shows `Sin datos ingestados` after loaded empty.
17. Real local regression was run for MX: `today`, `yesterday`, `last_7_days` all returned `PASSED` after capturing the missing `yesterday` range.
18. Frontend full check passed: lint, typecheck, tests.
19. Backend full check passed: ruff, mypy, pytest.

## Remaining Iteration 11 Fixes Carried Forward

No open blocker remains in the current codebase. Iteration 12 must preserve these contracts while replacing dashboard configuration.

ITERATION_11_STATUS = CLOSED
