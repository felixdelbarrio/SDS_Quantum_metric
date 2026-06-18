# Storage Decision

Decision: keep Parquet + Polars for Iteration 9.

Why:

- It matches the current offline analytical workload.
- It is portable and auditable.
- It keeps desktop operations simple.
- Existing performance issues are addressed by daily partitions, lazy scans and derived entities.

DuckDB is not introduced in this iteration because the current parity blockers are not SQL expressiveness blockers. If future work requires cross-dashboard joins or ad-hoc analytical SQL, DuckDB can be added as a query layer over Parquet with an explicit migration plan.
