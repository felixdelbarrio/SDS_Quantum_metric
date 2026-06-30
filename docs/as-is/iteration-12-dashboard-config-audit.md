# Iteration 12 Dashboard Config Audit

## Backend

- `backend/app/quantum/schemas.py`
  - `QuantumDashboardConfig` stores a single dashboard with `dashboard_id`, `name`, `dashboard_type`, `team_id`, `summary_tab`, `errors_tab`, `is_default`, `is_manual`, `validated` and fixed `widgets`.
  - Legacy migration creates `name="Dashboard default"` when only country-level `dashboard_id` exists.
  - If no dashboard is default, the first dashboard is automatically promoted. This prevents blocking saves without an explicit default.
  - `default_widget_configs()` is fixed to the nine mandatory Iteration 11 roles.

- `backend/app/quantum/config_store.py`
  - Reads/writes `config/quantum_config.json`.
  - Syncs only default dashboard fields to `.env`.
  - Does not store a discovered dashboard list separately from `countries[].dashboards`.

- `backend/app/quantum_dashboard/discovery.py`
  - Resolves one dashboard from config or URL.
  - Hardcodes tabs `Resumen` and `Errores`.
  - Does not list dashboards for a country.
  - Does not discover widget/card IDs from the selected dashboard.

- `backend/app/api/routes.py`
  - `_dashboard_from_discovery()` names discovered dashboards `Dashboard default` or `Dashboard manual`.
  - `/api/quantum/discover-dashboard` upserts one dashboard.
  - `/api/quantum/test-dashboard` is the manual ID validation path.
  - `_write_config()` contains a duplicated `ingestion_depth_days` keyword.

- `backend/app/ingestion/service.py`
  - Uses `country_config.default_dashboard()` and enabled widgets from that dashboard.
  - Capture receives the resolved dashboard ID/team ID.
  - Storage rows already include `dashboard_id`; scoping by dashboard is partial and needs explicit query/storage separation.

- `backend/app/storage/parquet_store.py`
  - `dashboard_id` is part of raw metadata.
  - Dataset listing exposes dashboard IDs when present.
  - Directory layout is still primarily country/range/dataset, not country/dashboard/range/dataset.

## Frontend

- `frontend/src/features/quantum-config/QuantumPage.tsx`
  - Shows `+ Dashboard manual` as the primary action in `Dashboards por pais`.
  - Renders one card per dashboard instead of a selector.
  - Lets `Nombre` be edited manually even for discovered dashboards.
  - Shows `Dashboard default` fallback text.
  - Default checkbox can only set a dashboard as default; it cannot uncheck and trigger validation.
  - Widget groups are fixed to `Resumen` and `Errores`.
  - `emptyDashboardConfig()` creates `Dashboard manual`.
  - `legacyDashboardConfig()` creates `Dashboard default`.

- `frontend/src/features/home/HomePage.tsx`
  - Uses country only; it does not display or select dashboard name.

- `frontend/src/features/datasets/DatasetsPage.tsx`
  - Entity metadata can show dashboard ID/widget role, but the page does not group datasets by dashboard as a first-class hierarchy.

## Code To Change

1. Add backend dashboard list discovery/cache model.
2. Add dashboard structure discovery model for tabs/widgets/types.
3. Replace one-dashboard discovery endpoint with country dashboard refresh and selected dashboard structure refresh.
4. Stop generating user-visible `Dashboard default`.
5. Replace manual dashboard primary UI with selector fed from discovered/cache dashboards.
6. Make default selection explicit and save-blocking.
7. Preserve fallback advanced manual only if hidden behind an advanced flow, or remove it.
8. Scope local dashboard/datasets by default dashboard and explicit `dashboard_id`.
