# Coverage Contract

Una ingesta solo puede terminar `completed` cuando el rango visible queda cubierto.

## Estados

| Condicion | Estado |
|---|---|
| Regresion falla | `failed_regression` |
| Faltan dias del rango | `failed_coverage_incomplete` |
| Faltan roles derivados no criticos | `completed_with_warnings` |
| Regresion y cobertura correctas | `completed` |

## Regla

Al finalizar la ingesta se llama a `resolve_range()` con:

- pais;
- `range_key`;
- `start_date`;
- `end_date`;
- estado de regresion.

El resultado se guarda en `job.details.coverage` y gobierna el estado final.

## UX

Home usa `/api/local-dashboard/coverage` para mostrar faltantes y lanzar `/api/ingestions/range` solo para el periodo visible.
