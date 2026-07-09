# Iteration 17 Dashboard Driven RCA

Fecha de auditoria: 2026-07-09.

## Sintomas

| Sintoma | Evidencia | Impacto |
|---|---|---|
| CO/SDS terminaba la ingesta pero Home mostraba `Sin datos locales suficientes` | La configuracion local tenia tabs `Overview general` y `Easy Dashboard Example`, pero el render local seguia esperando `Resumen` y `Errores` | Dashboard real de Colombia no era operable aunque hubiera datos y regresion |
| Los widgets genericos aparecian como faltantes obligatorios | El estado mezclaba roles genericos con el catalogo fijo MX de nueve cards | Falso `failed_missing_card` y mensajes tecnicos extensos |
| Home no mostraba tabs reales del dashboard | `DashboardTabs` estaba hardcodeado a `Resumen`/`Errores` | La UI no reflejaba la estructura real capturada de Quantum |
| La ingesta podia lanzarse varias veces para el mismo pais/rango/dashboard | No existia scope activo centralizado | Consumo innecesario de Chrome/CPU y estados de datos en carrera |
| Una ingesta podia finalizar aunque faltara cobertura del periodo | El resultado final dependia de regresion/build, no del contrato de dias requerido | Riesgo de publicar periodos incompletos como completos |

## Causa raiz

La aplicacion tenia soporte generico de widgets, pero todavia existian supuestos rigidos de dashboard:

- `widget_roles.py` derivaba `tab_index=0` como `summary` y `tab_index=1` como `errors`.
- `catalog.py` asignaba cualquier `generic.*` a `summary`.
- `capture.py` solo recorria dos tabs nominales.
- Home consultaba endpoints separados de summary/errors y renderizaba tabs fijas.
- `LocalDashboardService.status()` solo consideraba contratos visuales legacy y exponia faltantes tecnicos completos.

## Correccion

| Area | Cambio |
|---|---|
| Discovery/capture | Las tabs configuradas reales se propagan a captura y RAW (`tab`, `tab_name`, `tab_index`) |
| Roles genericos | `generic.<tab_index>.*` conserva su tab real y no fuerza `summary` |
| Builder | Persiste datasets dashboard-driven: `derived/dashboard_tabs`, `derived/dashboard_widgets`, `derived/widget_chart_payloads`, `derived/widget_table_payloads` |
| API local | Nuevo `GET /api/local-dashboard/dashboard` devuelve tabs y widgets reales en una sola respuesta |
| Home | Renderiza tabs dinamicas y widgets genericos sin hardcodear `Resumen`/`Errores` |
| Ingesta | Bloquea scope duplicado y marca `failed_coverage_incomplete` si el rango no queda cubierto |
| UX | Los detalles tecnicos largos quedan para Evidence/Datasets; Home recibe motivos accionables |

## Resultado local

| Pais | Dashboard | Range | Estado | Tabs | Widgets |
|---|---|---|---|---|---:|
| CO | SDS | `last_7_days` | `PASSED` | `Overview general`, `Easy Dashboard Example` | 11 |
| MX | Dashboard General MX | `last_7_days` | `PASSED` | `Resumen`, `Errores` desde configuracion | 9 |

## Codigo muerto evitado

No se duplicaron componentes por pais ni se introdujeron mocks. Los componentes legacy summary/errors se mantienen solo como compatibilidad de endpoints existentes; Home usa el contrato dinamico.
