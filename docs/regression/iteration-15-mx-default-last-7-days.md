# Iteration 15 MX Default Last 7 Days Regression

Date: 2026-07-07

## Verdict

`PASSED`

## Scope

- country: `MX`
- base_url: `https://bbvamx.quantummetric.com`
- dashboard_id: `8e53eb82-587c-4b92-a0fa-0f6283677e28`
- dashboard_name: `Dashboard General MX`
- team_id: `1da677de-9313-4b49-9110-81a6b756ca7e`
- range: `last_7_days`
- ingestion_id: `5c4d03fe-c72f-40ab-b2e7-507605fb6104`

## Capture Result

- status: `completed`
- planned_chunks: `1`
- completed_chunks: `1`
- calls_captured: `79`
- rows_captured: `151`
- mandatory_cards_captured: `9/9`
- derived_datasets: `7`
- regression_status: `passed`

## Web vs Local

| Tab | Card | Web value | Local value | Status | Difference |
| --- | --- | ---: | ---: | --- | ---: |
| summary | Paginas vistas | 7609172.0 | 7609172.0 | passed | 0.0 |
| summary | Sesiones | 1554152.0 | 1554152.0 | passed | 0.0 |
| summary | Sesiones con conversion | 281172.0 | 281172.0 | passed | 0.0 |
| summary | Tiempo medio de sesion | 98.52 | 98.52 | passed | 0.0 |
| summary | Detalle por APP Name y Sistema operativo | 10 visible rows | 12 local rows | passed | - |
| errors | Evolutivo - % Sesiones con Error | 96.0 | 96.0 | passed | 0.0 |
| errors | Top 20 Errores por nombre del error | 10 visible rows | 12 local rows | passed | - |
| errors | Comparativa de sesiones con error por App Name | 1823200.0 | 1823200.0 | passed | 0.0 |
| errors | % Sesiones con Error por App Name | 10 visible rows | 12 local rows | passed | - |

Table widgets pass because the first visible rows captured from Quantum Web match the local rows used by the dashboard. The local dataset can include additional rows beyond the visible Web sample.

## Dashboard Availability

`GET /api/local-dashboard/summary?country=MX&range_key=last_7_days` returned `status=ok` with 4 summary widgets.

`GET /api/local-dashboard/errors?country=MX&range_key=last_7_days` returned `status=ok` with 2 error widgets and the table endpoints read the corresponding local datasets.
