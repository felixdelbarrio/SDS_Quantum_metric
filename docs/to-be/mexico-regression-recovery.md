# Mexico Regression Recovery

Country: MX  
Dashboard: `Dashboard General MX`  
Dashboard ID: `8e53eb82-587c-4b92-a0fa-0f6283677e28`

The Mexico regression was caused by stale period selection. The builder now selects the latest requested/captured period for preset ranges and keeps dashboard IDs isolated.

Validation executed on 2026-07-07:

- widgets enabled/supported: 9;
- build result: 9/9 captured;
- regression: PASSED;
- Home status: `summary_ready=true`, `errors_ready=true`;
- no `Sin datos locales suficientes`;
- no local chart contractual failure.

Current `last_7_days` sample:

| Widget | Value |
|---|---:|
| Paginas vistas | 7609172 |
| Sesiones | 1554152 |
| Sesiones con conversion | 281172 |
| Tiempo medio de sesion | 98.52 |
| Evolutivo - % Sesiones con Error | 96 |
| Comparativa de sesiones con error por App Name | 2515913 |
