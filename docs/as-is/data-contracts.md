# Data Contracts

## Analytics request contract

```json
{
  "id": "uuid",
  "namespace": ["tenant-or-query-namespace"],
  "collections": {"namespace": [], "collections": []},
  "relationships": {"namespace": [], "relationships": []},
  "dimensions": {"namespace": [], "dimensions": []},
  "metrics": {"namespace": [], "metrics": []},
  "filter": {"namespace": [], "predicateFnNamespace": [], "arguments": [], "metadata": {}},
  "pagination": {"namespace": [], "limit": 10, "offset": 0},
  "ordering": {"namespace": [], "sorts": []},
  "dimensionFills": {"namespace": [], "dimensionFills": []},
  "metadata": {
    "dashboardId": "uuid",
    "cardId": "uuid",
    "cardType": "CHART|TABLE",
    "viewName": "dimensionQuery|timeSeriesQuery|coreMetrics|topN",
    "pathName": "/dashboard/{dashboardId}",
    "metricIds": ["uuid"],
    "slowQuery": false
  }
}
```

## Historical request contract

```json
{
  "query": {
    "...": "same shape as analytics request"
  },
  "ts": [1781244000, 1781261940],
  "historicalRequest": {
    "statistics": ["MEDIAN"],
    "period": 604800,
    "periodCount": 3
  }
}
```

## Analytics response contract

```json
{
  "id": "query id",
  "namespace": [],
  "project": {},
  "processed": true,
  "rows": [],
  "stats": {},
  "metadata": {
    "queryIds": []
  }
}
```

## Local persistence fields

Every raw call should store:

- `ingestion_id`
- `ingestion_ts`
- `country`
- `source_endpoint`
- `http_method`
- `status_code`
- `dashboard_id`
- `card_id`
- `card_type`
- `view_name`
- `metric_ids`
- `query_hash`
- `response_hash`
- `request_json_sanitized`
- `response_json`
- `row_count`
- `source_ts_start`
- `source_ts_end`

Derived datasets should normalize:

- `dashboard_id`
- `card_id`
- `view_name`
- `dimension_key`
- `dimension_value`
- `metric_key`
- `metric_value`
- `period_start`
- `period_end`
- `country`
- `ingestion_id`

## Partitioning

Required partition root:

```text
data/parquet/country=MX/
```

Initial datasets:

- `raw_api_calls`
- `dashboards`
- `cards`
- `metrics`
- `historical`
- `derived`
