# Quantum Web vs Local Regression

## Summary

- Final verdict: PASSED
- Regression status: passed
- Country: MX
- Ingestion ID: -
- Generated at: 2026-06-16T17:43:13.487080+00:00
- Tolerance: 0.1%

## Environment

- Source: local Parquet visual contracts and web snapshots
- Dashboard: general

## Dashboard Resolved

- Dashboard ID: dash-fixture
- Team ID: team-fixture

## Captured APIs

- See data/parquet/country=*/raw_api_calls

## Mandatory Cards

| Tab | Card | Web value | Local value | Status | Difference |
| --- | --- | ---: | ---: | --- | ---: |
| summary | Paginas vistas | 150.0 | 150.0 | passed | 0.0 |
| summary | Sesiones | 30.0 | 30.0 | passed | 0.0 |
| summary | Sesiones con conversion | 3.0 | 3.0 | passed | 0.0 |
| summary | Tiempo medio de sesion | 86.67 | 86.67 | passed | 0.0 |
| summary | Detalle por APP Name y Sistema operativo | 4.0 | 4.0 | passed | - |
| errors | Evolutivo - % Sesiones con Error | 16.67 | 16.67 | passed | 0.0 |
| errors | Top 20 Errores por nombre del error | 2.0 | 2.0 | passed | - |
| errors | Comparativa de sesiones con error por App Name | 5.0 | 5.0 | passed | 0.0 |
| errors | % Sesiones con Error por App Name | 2.0 | 2.0 | passed | - |

## Widget Comparison

Widget values are compared against the captured web snapshot values.

## Table Comparison

Tables compare visible row counts and first visible rows when snapshots include rows.

## Chart Comparison

Charts compare totals, point counts, and visible values where available.

## Chart Regression

| Tab | Card | Series | Axis X | Axis Y | Bands | Values | Status |
|---|---|---:|---|---|---|---|---|
| summary | Paginas vistas | - | passed | passed | passed | passed | passed |
| summary | Sesiones | - | passed | passed | passed | passed | passed |
| summary | Sesiones con conversion | - | passed | passed | passed | passed | passed |
| summary | Tiempo medio de sesion | - | passed | passed | passed | passed | passed |
| errors | Evolutivo - % Sesiones con Error | - | passed | passed | passed | passed | passed |
| errors | Comparativa de sesiones con error por App Name | - | passed | passed | passed | passed | passed |

## Table Regression

| Tab | Table | Columns | Rows | Expandable | Deltas | Colors | Status |
|---|---|---|---:|---|---|---|---|
| summary | Detalle por APP Name y Sistema operativo | checked | 4.0 | passed | passed | passed | passed |
| errors | Top 20 Errores por nombre del error | checked | 2.0 | passed | passed | passed | passed |
| errors | % Sesiones con Error por App Name | checked | 2.0 | passed | passed | passed | passed |

## Discrepancies

- None

## Final Verdict

PASSED
