# Table Deltas Contract

## Campos

`summary.detail_by_app_name_os` debe persistir, cuando Web/API los entregue:

- `page_views_delta_percent`
- `sessions_delta_percent`
- `conversions_delta_percent`
- `page_views_semantic_state`
- `sessions_semantic_state`
- `conversions_semantic_state`

## Semantica

El parser conserva valores fuente. Si Web no entrega color/intencion, el fallback actual clasifica delta positivo como `positive`, negativo como `negative` y ausente como `neutral`. La UI pinta color solo si existe valor delta; si el valor no existe, muestra `-`.

## Frontend

`SummaryDetailTable` renderiza deltas con signo, porcentaje y clase `semantic-*`. No calcula deltas en cliente.

## Regresion

Si Web contiene un delta y el derivado local no lo contiene, la regresion debe tratarlo como discrepancia de tabla.
