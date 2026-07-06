# Manual Dashboard Contract

Manual dashboards are first-class dashboard resources. They can be created for any country by pasting a Quantum dashboard URL or a dashboard ID.

## Supported URL

```text
https://bbvaco.quantummetric.com/#/dashboard/fccfa9f6-5d01-47cf-9ba6-b7bccd4d4f2b?dashboardUseGlobal=true&teamID=24feba5b-307d-40ed-83de-478111f8938e&ts=last_7_days
```

## Parsed fields

- `dashboard_id`: `fccfa9f6-5d01-47cf-9ba6-b7bccd4d4f2b`
- `team_id`: `24feba5b-307d-40ed-83de-478111f8938e`
- `base_url`: `https://bbvaco.quantummetric.com`
- `range_key`: `last_7_days`

## Validation

Manual dashboards are validated by loading the real dashboard structure from Quantum. A manual dashboard cannot be saved as valid if tabs/widgets cannot be recovered from Quantum or cache.
