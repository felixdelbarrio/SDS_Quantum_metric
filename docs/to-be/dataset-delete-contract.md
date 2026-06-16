# Dataset Delete Contract

## API

```http
DELETE /api/datasets/{country}?confirm={country}
```

If `confirm` differs from `country`, the API returns `400`.

## Backend Behavior

`ParquetStore.delete_country_all` removes:

- `parquet/country={country}` including RAW, contracts, snapshots, derived datasets and regression datasets.
- Country rows from `manifests/ingestion_manifest.parquet`.
- Country-scoped runtime/cache and export files when their filename or directory name includes the country token.

The response includes:

```json
{
  "country": "MX",
  "deleted_datasets": [],
  "deleted_ingestions": 0,
  "deleted_files": 0,
  "deleted_bytes": 0,
  "status": "deleted"
}
```

The in-memory ingestion service also purges active and completed jobs for that country.
