# Iteration 15 CO SDS Last 7 Days Regression

Date: 2026-07-07

## Verdict

`PASSED`

## Scope

- country: `CO`
- base_url: `https://bbvaco.quantummetric.com`
- dashboard_id: `fccfa9f6-5d01-47cf-9ba6-b7bccd4d4f2b`
- dashboard_name: `SDS`
- team_id: `24feba5b-307d-40ed-83de-478111f8938e`
- range: `last_7_days`
- ingestion_id: `9f17f495-f2d0-4c13-a3a4-beefb3dcfe89`

## Capture Result

- status: `completed`
- planned_chunks: `1`
- completed_chunks: `1`
- calls_captured: `45`
- rows_captured: `565`
- mandatory_cards_captured: `1/1`
- derived_datasets: `1`
- regression_status: `passed`

## Web vs Local

| Tab | Card | Web value | Local value | Status | Difference |
| --- | --- | ---: | ---: | --- | ---: |
| summary | Sesiones | 6504.0 | 6504.0 | passed | 0.0 |

## Dashboard Availability

`GET /api/local-dashboard/summary?country=CO&range_key=last_7_days` returned `status=ok` with one widget:

- role: `summary.sessions`
- title: `Sesiones`
- value: `6504.0`

The SDS dashboard currently exposes one enabled/supported mapped widget. Unsupported widgets were not included in the parity claim.
