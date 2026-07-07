# GraphQL Dashboard Resources Contract

## Endpoint

`POST https://api.quantummetric.com/query`

## Operation

`resourcesList`

## Variables

- `userId`: resolved from the authenticated Quantum session or intercepted request.
- `resourceFilter.namePrefix`: empty string.
- `resourceFilter.types`: `["DASHBOARD"]`.
- `resourceFilter.isStarredByUser`: `false`.
- `pagination.first`: zero-based page offset.
- `pagination.size`: default 25.
- `pagination.orderBy`: `LAST_EDITED_AT`.
- `pagination.order`: `Desc`.

## Local model

- `dashboard_id`: Quantum `id`.
- `name`: Quantum `name`.
- `type`: `DASHBOARD`.
- `starred`: Quantum `starred`.
- `country`: local country scope.
- `source`: `quantum_graphql`, `manual` or `cache`.
- `stale`: true when a cached dashboard disappeared from a refresh.

## Cache

Dashboard resources are stored in `config/dashboard_resources/<country>.json`. The file contains no cookies, Authorization headers or session values.
