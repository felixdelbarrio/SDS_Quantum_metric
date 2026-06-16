# Parquet Derived Datasets

Iteration 4 keeps raw API calls and adds contract-oriented datasets:

```text
data/parquet/
└── country=MX/
    ├── raw_api_calls/
    ├── dashboard_cards/
    ├── web_snapshots/
    ├── visual_contracts/
    ├── derived/
    │   ├── summary_widgets/
    │   ├── summary_detail_table/
    │   ├── errors_widgets/
    │   ├── errors_top_errors_table/
    │   ├── errors_app_name_table/
    │   └── timeseries/
    └── regression/
        ├── web_vs_local_results/
        └── discrepancies/
```

Raw rows include sanitized request headers. Cookie, Authorization, CSRF and token-like headers are dropped before persistence.

Derived rows are written during ingestion or by:

```bash
POST /api/datasets/MX/regenerate-derived
```

Regression can be rerun with:

```bash
python -m backend.app.quantum_dashboard.regression --country MX --dashboard general
POST /api/datasets/MX/regression
```
