# Iteracion 5 Refactor Design

## Dashboard

Home consume solo endpoints `local-dashboard/*`. Los widgets reciben `chart_payload` desde Parquet y `QuantumChart` renderiza SVG con ejes, leyenda, series, bandas y periodo. Si no hay contrato grafico, la UI muestra ausencia de contrato en vez de inventar una curva.

## Cards Expandibles

Cada KPI y donut abre un modal local con grafico amplio, tabla de puntos y export CSV. No hay acceso a videos; el modal muestra el aviso de producto correspondiente.

## Tablas

`summary_detail_table` conserva jerarquia `row_id`, `parent_row_id`, `depth`, `is_expandable`, deltas y estados semanticos. React solo expande/colapsa y pinta clases semanticas.

## Errores

La pestana Errores usa grid 2x2: evolutivo, Top 20, donut comparativo y tabla de porcentaje por App Name.

## Ingesta

La profundidad por defecto es 365 dias. Sin datos se ingesta `hoy - depth_days` hasta hoy; con datos se reingestan solo los dias configurados por `QUANTUM_INCREMENTAL_REPROCESS_DAYS`.

## Datasets

Datasets muestra paises, KPIs, acciones y una consola de entidades Parquet con paginacion, schema y filas RAW/derivadas bajo demanda.
