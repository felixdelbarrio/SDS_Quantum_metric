# Chart Contract

`ChartPayload` es el contrato canonico para graficas locales.

Campos principales:

- `chart_type`: `line`, `bar`, `donut` o `table`.
- `x_axis` y `y_axis`: min/max, unidad, etiqueta y ticks.
- `series`: series visibles. Line charts deben conservar Mobile y Desktop.
- `bands`: bandas grises o anotaciones si Quantum las entrega.
- `legends`: leyendas visibles.
- `period_label`, `granularity`, `timezone`.

Persistencia:

`data/parquet/country={country}/derived/chart_payloads/`

Cada fila conserva pais, ingesta, dashboard, tab, card, hashes fuente, periodo, timezone y payload serializado.

Regla:

React no interpola ni crea series. Si falta `chart_payload`, la card no dibuja una curva local.
