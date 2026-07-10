# Iteration 17 MX Default Last 7 Days Regression

Verdict: PASSED  
Country: MX  
Dashboard: Dashboard General MX  
Dashboard ID: `8e53eb82-587c-4b92-a0fa-0f6283677e28`  
Range: `last_7_days`  
Executed: 2026-07-09  
Period: `2026-07-01T06:00:00Z` -> `2026-07-07T08:59:59Z`

| Tab | Widget | Status | Local |
|---|---|---|---:|
| Resumen | Paginas vistas | passed | 7609172 |
| Resumen | Sesiones | passed | 1554152 |
| Resumen | Sesiones con conversion | passed | 281172 |
| Resumen | Tiempo medio de sesion | passed | 98.52 s |
| Errores | Evolutivo - % Sesiones con Error | passed | 96.0% |
| Errores | Comparativa de sesiones con error por App Name | passed | 2515913 |

Notes:

- The dashboard endpoint groups legacy MX data under configured tabs without duplicating `Resumen`.
- Values come from the local Parquet/regression state available on 2026-07-09.
