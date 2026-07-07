# Iteration 14 Quantum Web Audit

Date: 2026-07-06

## Dashboard list flow

Quantum Web lists dashboards through the shared GraphQL endpoint, not through a REST dashboard menu endpoint. The user-provided network capture in `Quantum Metrics - Iteracion 14.pdf` shows the dashboard menu calling `POST https://api.quantummetric.com/query` with operation `resourcesList`.

A Playwright audit was attempted from the local controlled profile on 2026-07-06. The browser reached `bbvamx.quantummetric.com` but redirected to authentication, so no new authenticated payload could be captured in this run. The fallback used for implementation is the real network capture from the attached PDF plus the existing iteration 13 audit in `docs/as-is/iteration-13-dashboard-discovery-audit.md`.

## GraphQL endpoint

`POST https://api.quantummetric.com/query`

## Request

```graphql
query resourcesList($userId: ID!, $resourceFilter: ResourceFilter, $pagination: PaginationInfo) {
  resources(userId: $userId, filter: $resourceFilter, pagination: $pagination) {
    totalCount
    resources {
      id
      type
      name
      starred
    }
  }
}
```

## Variables

```json
{
  "userId": "<sanitized-user-id>",
  "resourceFilter": {
    "namePrefix": "",
    "types": ["DASHBOARD"],
    "isStarredByUser": false
  },
  "pagination": {
    "first": 0,
    "size": 25,
    "orderBy": "LAST_EDITED_AT",
    "order": "Desc"
  }
}
```

## Pagination behavior

The response contract includes `totalCount`. The local implementation requests pages of 25 and increments `pagination.first` until all dashboards are fetched. It does not silently stop at 25.

## User ID resolution

In Quantum Web the `userId` is present in authenticated GraphQL requests. The implementation resolves it from the authenticated session abstraction for tests and from intercepted request variables during Playwright discovery. If there is no authenticated request, discovery fails and falls back to local dashboard resources cache.

## Response contract

| Field | Meaning |
|---|---|
| id | internal dashboard_id |
| name | visible dashboard name |
| type | DASHBOARD |
| starred | user starred state |

## Dashboard structure flow

The structure is loaded with GraphQL `LoadDashboard($dashboardId: ID!)` through the same `/query` endpoint. The dashboard entity includes serialized `tabs`; each tab contains `layoutCardsMap` with the real widgets for that tab.

## Tabs/widgets discovery flow

`LoadDashboard -> entity.tabs -> layoutCardsMap` is the canonical path. Tabs are preserved by `tab_id`, `tab_index` and visible `name`. Widgets are mapped to `widget_id`, `card_id`, title, tab, type and local visual role where recognized.

## Current local gaps

- The previous configuration screen rendered every country simultaneously.
- The dashboard button reused discovery but did not expose a dedicated resources cache contract.
- Legacy migrations could display a dashboard ID as the dashboard name.
- Manual dashboards were intentionally not exposed by the previous route test.
- Frontend grouping accepted broad tab-index matches that could mix widgets.

## Implementation plan

- Add a `dashboard_resources` service for paginated `resourcesList`.
- Persist sanitized resources in `config/dashboard_resources/<country>.json`.
- Expose `GET /api/quantum/countries/{country}/dashboards` and `POST /api/quantum/countries/{country}/dashboards/refresh`.
- Add manual dashboard parsing and validation by URL or dashboard ID.
- Redesign configuration around one selected country.
- Keep dashboard ID as value and `name` as label.
- Render tabs strictly and send unsupported widgets through disabled controls.

## Code to delete

- Legacy behavior that substitutes `dashboard_id` into `name`.
- Tests that assert manual dashboard routes are absent.
- Frontend rendering that shows country cards for every geography in the main Quantum configuration flow.
