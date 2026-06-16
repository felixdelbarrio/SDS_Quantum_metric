# Automatic Derived and Regression Pipeline

## Ingestion Pipeline

After capture, ingestion automatically runs:

1. RAW merge into Parquet.
2. Visual contract generation.
3. Derived dataset generation.
4. Chart payload persistence.
5. Today regression report.
6. Last-7-days regression report.
7. Final job status update.

## User Experience

The final user does not see buttons for derivative rebuilds, regression execution or audit execution. Datasets is an inspection console, not a maintenance console.

## Failure Model

- Parser or mandatory card failures are persisted as evidence.
- Missing chart payloads fail the build/regression contract.
- Any failed range report blocks `completed`.
