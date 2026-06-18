# Web Local Evidence Chain

For each configured widget role the evidence chain is:

1. Web visible value.
2. Web DOM/snapshot value captured during ingestion.
3. Quantum request hash.
4. Quantum response hash.
5. Raw Parquet path.
6. Derived Parquet path.
7. Local API value.
8. UI payload.

The backend entry point is:

`GET /api/datasets/{country}/evidence`

Statuses:

- `matched`
- `missing_contract`
- `missing_web_snapshot`
- `missing_derived`
- `diverged_parser`
- `diverged_aggregation`
- `diverged_local_api`

This is the debugging path for any Web vs Local mismatch.
