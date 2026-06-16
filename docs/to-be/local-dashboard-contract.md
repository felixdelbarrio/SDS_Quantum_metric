# Local Dashboard Contract

Home reads from `/api/local-dashboard/*`, which serves derived Parquet datasets rather than parsing raw Quantum responses at request time.

Endpoints:

- `GET /api/local-dashboard/countries`
- `GET /api/local-dashboard/status?country=MX`
- `GET /api/local-dashboard/summary?country=MX`
- `GET /api/local-dashboard/summary/table?country=MX&search=&sort=page_views&direction=desc`
- `GET /api/local-dashboard/errors?country=MX`
- `GET /api/local-dashboard/errors/top-errors?country=MX&search=&sort=error_sessions&direction=desc`
- `GET /api/local-dashboard/errors/app-name?country=MX&search=&sort=error_session_percent&direction=desc`

Readiness requires:

- visual contracts for all mandatory roles;
- web snapshots;
- derived summary widgets/table;
- derived errors widgets/tables;
- latest regression status `passed` or `passed_with_tolerance`.

If raw data exists without derived datasets, status returns a reason telling the user to regenerate derivatives or run a new ingestion.
