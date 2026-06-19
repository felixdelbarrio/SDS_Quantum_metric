# Reglas de agregacion por rango Quantum

## Principio

No todos los widgets se pueden agregar desde dias sueltos. Cuando Quantum Web calcula el valor
con una ventana completa, la app local debe capturar esa misma ventana y persistirla como contrato
de rango.

## Tabla de reglas

| Role | Regla | Motivo |
|---|---|---|
| `summary.page_views` | `sum` | Conteo aditivo. |
| `summary.sessions` | `sum` | Conteo aditivo. |
| `summary.converted_sessions` | `quantum_range_contract_required` | Conversion depende de la definicion de sesion/rango de Quantum. |
| `summary.avg_session_duration` | `weighted_average` | Media ponderada por sesiones, no media simple por dia. |
| `summary.detail_by_app_name_os` | `quantum_range_contract_required` | Tabla jerarquica con comparativas de rango. |
| `errors.error_sessions_percentage_evolution` | `ratio` | Porcentaje derivado de numerador/denominador del rango. |
| `errors.top_errors_by_error_name` | `quantum_range_contract_required` | Ranking y deltas calculados por Quantum sobre la ventana. |
| `errors.error_sessions_by_app_name_comparison` | `quantum_range_contract_required` | Comparativa visual calculada por rango completo. |
| `errors.error_session_percentage_by_app_name` | `quantum_range_contract_required` | Porcentaje por app name con ordenacion de Quantum. |

## Implementacion

La fuente canonica vive en `backend/app/quantum_dashboard/aggregation_rules.py`.
`builder.py`, `service.py` y `regression.py` deben tratar un widget con
`quantum_range_contract_required` como no agregable desde particiones parciales.

## Criterio de aceptacion

Today, Yesterday y Last 7 Days solo pueden mostrarse como `complete` cuando existe el contrato
capturado para ese `range_key` y la regresion asociada pasa.

