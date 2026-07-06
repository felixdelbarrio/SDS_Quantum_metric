# Last 7 Days Widget Regression

The regression scope is `country + dashboard_id + widget_id + range_key`.

For `last_7_days`, every enabled and supported widget must compare:

- visible value;
- chart payload;
- table rows;
- deltas;
- percentages;
- decimals;
- period labels;
- timezone;
- ordering.

The report is written to `docs/regression/iteration-14-last-7-days-dashboard-<dashboard_id>.md` and `.json`.
