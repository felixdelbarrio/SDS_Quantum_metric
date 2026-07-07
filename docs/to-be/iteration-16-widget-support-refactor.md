# Iteration 16 Widget Support Refactor

Support is now capability based:

- known `visual_role` -> specific parser from the catalog;
- unknown CHART/KPI -> `generic_metric_card_v1`;
- unknown TABLE -> `generic_table_card_v1`;
- unknown DONUT -> `generic_donut_card_v1`;
- unknown type -> unsupported with an actionable reason.

`backend/app/quantum_dashboard/widget_support.py` owns the support decision. `dashboard_structure.py` and schema migration use that decision so configuration, ingestion, builder, UI and regression agree.

Generic widgets receive stable roles:

```text
generic.<tab_index>.<kind>.<widget_id_or_card_id>
```

The builder resolves calls through widget descriptors and can assign ambiguous TABLE calls by descriptor sequence when Quantum emits a shared temporary `card_id`.

Non-widget telemetry such as `navbarMetricsQuery` and `dashboardReplayQuery` is excluded before derived datasets are built.
