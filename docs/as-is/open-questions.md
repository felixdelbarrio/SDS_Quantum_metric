# Open Questions

1. Which dashboards beyond `Dashboard General MX` must be ingested in iteration 1?
2. Should the ingestion navigate only known dashboard URLs or enumerate dashboards through `resources` GraphQL?
3. Which countries map to which Quantum Metric tenant/team/dashboard combinations?
4. Are all countries available under the same `bbvamx` tenant, or does each country use a different base URL?
5. Which historical ranges are business-required: today, last 7 days, rolling month, custom?
6. Should raw analytics responses be exported as-is, or should sensitive business dimensions be masked in ZIP exports?
7. What is the expected retention policy for local Parquet?
8. Should import merge conflicts be resolved by `query_hash + response_hash`, by source timestamps, or by ingestion priority?
9. Which report/release signing requirements apply for macOS and Windows builds?
10. GitHub branch protections require repository admin/API access; confirm whether they should be applied manually or through GitHub tooling.
