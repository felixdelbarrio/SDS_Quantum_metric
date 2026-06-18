# Ingestion Failure RCA

## Failing ingestions

| ID | Started | Finished | Status | Failure |
|---|---|---|---|---|
| `1dace7c7-bdbc-45cf-8c9a-44cd25b1bf8a` | 2026-06-18T11:42:54Z | 2026-06-18T11:47:01Z | failed | Polars schema inference failed while appending mixed row values. |
| `deb4fd45-9ffd-4dfd-8871-d037361dd362` | 2026-06-18T12:01:56Z | 2026-06-18T12:06:02Z | failed | Same Polars schema inference failure. |
| `534e8a97-f07f-485e-a343-46e347046502` | 2026-06-18T12:14:05Z | 2026-06-18T12:18:11Z | failed | Same Polars schema inference failure. |
| `e0ccfb68-3396-41b0-91bd-ec8992dd1b0e` | 2026-06-18T14:24:57Z | 2026-06-18T14:24:58Z | failed | Playwright context startup/teardown failed in the local environment. |

## Root cause

Primary fixed root cause: raw ingestion merge constructed a Polars `DataFrame` directly from heterogeneous captured rows. Some rows carried source timestamps as strings while others carried datetime-like values, so Polars inferred an incompatible schema and aborted persistence.

Secondary environmental finding: one later attempt failed before capture with a Playwright context manager error. The capture code already uses `sync_playwright().start()` correctly; this points to a local Playwright runtime/session issue rather than a Parquet schema issue.

## Evidence

- Persisted manifests in the active user data dir show repeated failures after 2026-06-18 09:31:05.
- The repeated message was: `could not append value ... of type: str to the builder`.
- The latest manifest records: `'PlaywrightContextManager' object has no attribute '_playwright'`.
- Successful ingestions before those failures captured 9/9 mandatory cards and produced derived datasets/regression.

## Files affected

- `backend/app/storage/parquet_store.py`
- `backend/app/ingestion/service.py`
- `backend/app/ingestion/capture.py`
- `backend/app/quantum_dashboard/builder.py`
- `backend/app/quantum_dashboard/regression.py`

## Fix

- Raw calls are normalized through `_parquet_safe_row` before Polars frame creation.
- Daily raw partition writes use the same normalization.
- Ingestion failures now persist sanitized failure metadata: stage, endpoint, chunk index and chunk bounds.
- Ingestion now fails clearly if no validated dashboard exists for a country.
- Ingestion filters disabled widget roles before persistence/derivation/regression.

## Validation

- Targeted backend tests pass for config persistence, range query, evidence and config-driven disabled widget filtering.
- `mypy backend desktop` passes.
- Full validation is completed through `make CI` and `make build` before PR.

## Remaining risks

- A real Quantum session is still required to prove a new capture after the Playwright environmental failure.
- If Playwright browser assets are corrupted locally, `make setup` or the packaged browser bootstrap must be re-run.
