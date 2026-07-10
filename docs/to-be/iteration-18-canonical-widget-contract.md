# Contrato canónico de widget

`QuantumWidgetContract` (`backend/app/quantum_dashboard/contracts.py`) es la única entidad que Home puede consumir. Incluye identidad Dashboard/Tab/Section/Widget, layout, display, comparación, gráfico, tabla, rango, timezone, hashes, parser version y estado.

`DisplayNumberContract` separa `raw_value` de `display_value` y conserva escala, precisión, prefijo, sufijo, formatter y cadena ya formateada. `HistoricalComparisonContract` conserva texto, delta mostrado e intención semántica. Un widget ambiguo o inválido no se convierte en contrato `resolved`.

Invariantes:

- una serie temporal no determina el KPI principal;
- `formatted` tiene prioridad de representación;
- no se escala un porcentaje por magnitud o título;
- periodo, labels, ticks y leyendas no se regeneran;
- cada fila conserva request/response/query hash.
