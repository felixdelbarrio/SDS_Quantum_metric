# Storage Architecture Audit

## Current model

The application persists Quantum captures under the user data directory in Parquet:

- `parquet/country=<country>/raw_api_calls/raw_api_calls.parquet`
- `parquet/country=<country>/day=YYYY-MM-DD/raw_api_calls/raw_api_calls.parquet`
- `parquet/country=<country>/derived/*`
- `parquet/country=<country>/regression/*`
- `parquet/country=<country>/manifests/day_coverage.parquet`

Configuration is now persisted separately in `config/quantum_config.json` with schema version `2`.

## Query patterns

- Home reads derived datasets only.
- Datasets can inspect RAW, but paginates entities.
- Coverage uses day manifests first, then source ranges.
- Regression compares visual contracts, web snapshots and derived rows.

## Ingestion patterns

- Ingestion captures real Quantum `/analytics` and `/analytics/historical` calls.
- Captures are merged by source range and deduplicated by endpoint, dashboard, card and hashes.
- Raw calls are republished into daily partitions after every merge.
- Derived datasets and regression are rebuilt after each captured chunk.

## Regression patterns

Regression needs immutable evidence for each role:

- visual contract;
- web snapshot;
- raw request/response hashes;
- derived row;
- local API value.

Iteration 9 adds `backend/app/quantum_dashboard/evidence.py` for this chain.

## Pain points

- Old config only represented one dashboard per country and did not persist widgets.
- Raw merge built a Polars frame from heterogeneous Python values, which could fail when rows mixed strings and datetimes.
- Coverage treated all ranges similarly and could over-warn for Today.
- Datasets exposed entities too flatly for discrepancy analysis.

## Candidate options

- Parquet + Polars: strong fit for portable analytical files, lazy scans, local export/import, low operational burden.
- Parquet + DuckDB: good SQL layer over Parquet, useful future option for cross-file joins, but not needed for current derived entity queries.
- SQLite: simple and indexed, but weaker for nested JSON-heavy raw payloads and columnar scans.
- DuckDB persistent: excellent analytics, but adds another persistence model and migration burden right now.
- PostgreSQL local: too heavy for a desktop app.
- Mongo-compatible open source: flexible documents, but weaker for local analytical range scans and exportable columnar entities.
- OpenSearch: over-sized for desktop, higher memory and operational cost.

## Decision matrix

| Criteria | Parquet | DuckDB | SQLite | Other |
|---|---:|---:|---:|---:|
| Portable export/import | 5 | 4 | 4 | 2 |
| Range analytics | 4 | 5 | 3 | 3 |
| Nested raw payloads | 4 | 4 | 3 | 4 |
| Low CPU/memory | 4 | 4 | 4 | 2 |
| Desktop simplicity | 5 | 4 | 5 | 2 |
| Current code fit | 5 | 3 | 2 | 1 |
| Auditability | 5 | 4 | 3 | 3 |

## Decision

Keep Parquet + Polars as the persistence model for Iteration 9. Do not introduce a second database yet.

Reasoning:

- Existing queries already target derived Parquet entities, not RAW scans.
- Daily partitions plus `day_coverage.parquet` satisfy range detection.
- Export/import remains transparent and file based.
- The main parity gaps were config, range resolution and evidence, not Parquet itself.

DuckDB remains a future query engine candidate if cross-dashboard joins or heavier ad-hoc analytics become common, but it should be introduced as a query layer over Parquet only with an explicit migration plan.

## Migration plan

Implemented in Iteration 9:

- Move config writes to `config/quantum_config.json`.
- Migrate reads from legacy `config/quantum.json`.
- Normalize raw rows before Polars frame creation.
- Add range resolution and evidence modules.
- Enrich dataset entity metadata with category, dashboard ID and widget role.

## Code to delete

No storage model is deleted in this iteration because Parquet remains the chosen model. Legacy config read support is retained only as a one-time migration path from `quantum.json` to `quantum_config.json`; new writes use the new file.

## Risks

- Real Web parity still depends on a valid Quantum browser session.
- The latest local manifest also shows a Playwright environment failure; setup/build must keep bundled browser assets healthy.
- DuckDB may become useful later if local custom ranges require multi-dashboard SQL joins.
