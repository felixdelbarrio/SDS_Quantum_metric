# Quantum Web Regression - As Is

Before Iteration 4 the local app persisted generic Quantum API calls and then tried to infer dashboard metrics from arbitrary `response_json.rows` shapes.

Observed gaps:

- Raw calls and row counts could exist while Home still showed no usable metrics.
- The ingestion success state did not prove that visible Quantum Web cards had been captured.
- Summary and Errors tabs were not represented as explicit dashboard/card contracts.
- There was no Web vs Local regression report.
- Local APIs interpreted raw Quantum JSON at request time instead of serving derived analytical datasets.

Iteration 4 changes the acceptance unit from "raw call" to:

- dashboard
- tab
- card
- query
- response
- visual contract
- web snapshot
- derived dataset
- regression result

The current implementation supports fixture-based CI regression and real-capture plumbing. A real Quantum Web run must still be executed with an authenticated browser session to replace fixture evidence with production dashboard evidence.
