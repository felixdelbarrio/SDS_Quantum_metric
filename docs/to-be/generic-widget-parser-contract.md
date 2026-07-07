# Generic Widget Parser Contract

Generic parsers consume real Quantum responses only. They do not fabricate values.

## Generic Metric

Input: CHART or KPI response with visible value, metric rows or time series.

Output:

- `value`;
- inferred `unit` (`count` or `percent`);
- `timeseries` when present;
- `chart_payload` when points exist;
- `period` and source hashes through the builder.

## Generic Table

Input: TABLE response with `rows[].dimensions` and `rows[].metrics`, or flattened row values.

Output:

- normalized `table_columns`;
- ordered `table_rows`;
- dynamic `dimension_N` and `metric_N` fields;
- `chart_type=table`;
- regression signature comparing row names, dimensions and metrics.

## Generic Donut

Input: DONUT/PIE-like response with series or dimension/metric rows.

Output:

- total;
- segments;
- donut `chart_payload`.

If a parser cannot find parseable structure, it returns a widget-specific parse error and regression cannot pass.
