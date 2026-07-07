# Iteration 16 Widget Support RCA

Fecha de auditoria: 2026-07-07.

## Colombia RCA

| Symptom | Root cause | Evidence | Fix |
|---|---|---|---|
| SDS mostraba widgets `CHART/TABLE no soportado` | El soporte dependia de roles/titulos conocidos del dashboard MX | CO/SDS tiene 11 widgets reales; 10 no tenian rol especifico | Se introdujo soporte por capacidad: CHART/KPI, TABLE y DONUT usan roles `generic.*` y parsers genericos |
| Dos tablas de Overview no llegaban a derivados | Quantum emite ambas con el mismo `card_id` temporal y sin `widget_id` real | Raw `card_id=ca5fdb29...` contiene dos respuestas `table` con filas distintas | El resolvedor asigna llamadas ambiguas por secuencia de descriptor y tab |
| `Top Navigation Errors` quedaba en parser error | La reescritura estricta del rango descartaba la query TABLE nativa; solo quedaban historicos 502 | Captura temporal mostro `/analytics` `topN/table` 200 con 3 filas; raw anterior solo tenia `table:historical` 502 | Las TABLE nativas preservan el rango que Quantum genera por `ts=last_7_days` y no se bloquean por esa validacion |
| Sessions podia salir de `navbarMetricsQuery` | Query de navegacion no es widget pero se mapeaba como `summary.sessions` | Valor local 6759 competia con card real `Sessions=15966` | Builder y mapper excluyen `navbarMetricsQuery`/`dashboardReplayQuery` como widgets |

## Mexico RCA

| Symptom | Root cause | Evidence | Fix |
|---|---|---|---|
| Home MX mostraba `Sin datos locales suficientes` para `last_7_days` | Raw/derived mezclaban periodos antiguos y actuales; el primer periodo leido podia ser junio | Rebuild local recupero `2026-07-01..2026-07-07`; status actual 9/9 passed | Builder filtra por el ultimo rango capturado usando `range_*`/`capture_chunk_*` y no por orden fisico del parquet |
| `Fallo contractual de grafica local` con valor visible | Charts agregados sin `chart_payload` completo | Regresion estricta fallaba si habia serie sin contrato grafico | Los parsers y builder persisten `chart_payload`; regresion busca widgets por rol en ambos datasets |

## Unsupported widgets analysis

| Country | Dashboard | Tab | Widget | Type | Current support | Expected support | Parser |
|---|---|---|---|---|---|---|---|
| CO | SDS | Overview general | SDS Score General | CHART | generic supported | supported | generic_metric_card_v1 |
| CO | SDS | Overview general | SDS Score - Tecnico | CHART | generic supported | supported | generic_metric_card_v1 |
| CO | SDS | Overview general | SDS - Usabilidad | CHART | generic supported | supported | generic_metric_card_v1 |
| CO | SDS | Overview general | Pago Nominas - CR general >1 interaccion | CHART | generic supported | supported | generic_metric_card_v1 |
| CO | SDS | Overview general | Tabla errores usabilidad | TABLE | generic supported | supported | generic_table_card_v1 |
| CO | SDS | Overview general | Tabla errores tecnico | TABLE | generic supported | supported | generic_table_card_v1 |
| CO | SDS | Easy Dashboard Example | Sessions | CHART | specific supported | supported | timeseries_metric_card_v1 |
| CO | SDS | Easy Dashboard Example | Navigation Error Rate | CHART | generic supported | supported | generic_metric_card_v1 |
| CO | SDS | Easy Dashboard Example | Task Success Rate | CHART | generic supported | supported | generic_metric_card_v1 |
| CO | SDS | Easy Dashboard Example | Experience Health Score | CHART | generic supported | supported | generic_metric_card_v1 |
| CO | SDS | Easy Dashboard Example | Top Navigation Errors | TABLE | generic supported | supported | generic_table_card_v1 |
| MX | Dashboard General MX | Resumen/Errores | 9 widgets default | CHART/TABLE/DONUT | specific supported | supported | specific role parsers |

## Missing derived analysis

| Country | Dashboard | Range | Expected dataset | Current state | Root cause |
|---|---|---|---|---|---|
| CO | SDS | last_7_days | visual_contracts, summary/errors widgets, chart_payloads, regression | PASSED 11/11 | Fixed ambiguous table metadata and native table range capture |
| MX | Dashboard General MX | last_7_days | derived/summary, summary_detail_table, errors, chart_payloads | PASSED 9/9 | Fixed latest-period selection |

## Code to delete

No dead compatibility shim was kept for unsupported widget titles. Non-widget queries are ignored centrally instead of patched per dashboard.

## Implementation plan

Implemented in this iteration:

1. Central support assessment in `widget_support.py`.
2. Generic role/spec/parser flow for unknown CHART/KPI, TABLE and DONUT widgets.
3. Descriptor-based role resolution by `widget_id`, `card_id` and ordered fallback for ambiguous table calls.
4. Native range preservation for Quantum TABLE queries that break under forced time rewriting.
5. Regression and Home services read dynamic widget placement without assuming MX-only tabs.
