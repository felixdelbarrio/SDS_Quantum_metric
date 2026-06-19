# Iteration 9 Final Architecture

## Principle

Quantum Web remains the source of truth. Local rendering uses only local persistence after ingestion; it does not call Quantum during visualization.

## Persistence

The selected persistence is Parquet + Polars:

- RAW API calls are compacted and republished into daily partitions.
- Derived entities are materialized by widget role.
- Regression and evidence are persisted as first-class datasets.
- Config is stored in `config/quantum_config.json`.

## Configuration

Configuration is schema-versioned and contains:

- browser;
- session mode;
- theme preference;
- ingestion depth;
- countries;
- default country;
- dashboards per country;
- default dashboard per country;
- widget IDs, types and enabled flags.

Manual cookies are never persisted.

## Ingestion

Ingestion resolves the country default dashboard, validates that it exists, captures only enabled widget roles and rebuilds derived data plus regression.

If no validated dashboard exists, ingestion fails with:

`No hay dashboard validado para <country>. Ve a Configuracion y ejecuta Test pais o Test dashboard.`

## Range resolution

`backend/app/quantum_dashboard/range_query.py` resolves required, covered and missing days per range. Today partial coverage is informational; historical ranges warn when required days are missing.

## Evidence

`backend/app/quantum_dashboard/evidence.py` links web visible value, raw hashes, Parquet paths, derived paths and local API value. It identifies the first divergence point for parser/aggregation/local API issues.

## Datasets

Datasets are grouped by country and enriched with entity category, dashboard ID and widget role. Export/import includes config and Parquet, while rejecting secret-looking payloads.
