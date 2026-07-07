# Colombia SDS Validation

Country: CO  
Base URL: `https://bbvaco.quantummetric.com`  
Dashboard: `SDS`  
Dashboard ID: `fccfa9f6-5d01-47cf-9ba6-b7bccd4d4f2b`  
Team ID: `24feba5b-307d-40ed-83de-478111f8938e`

Validation executed on 2026-07-07:

- dashboards in config/cache: 15;
- default dashboard ready: yes;
- widgets enabled/supported: 11;
- ingestion: `last_7_days`, status `completed`;
- captured cards: 11/11;
- regression: PASSED.

Notable TABLE rows captured from Quantum Web:

| Widget | Row | Value |
|---|---:|---:|
| Tabla errores usabilidad | Possible Frustration | 28 |
| Tabla errores usabilidad | Rage Click | 23 |
| Tabla errores usabilidad | Rage Scroll | 15 |
| Tabla errores tecnico | Long Running Spinner | 436 |
| Tabla errores tecnico | Datalayer Error | 98 |
| Tabla errores tecnico | Pago Nominas - Error de firma | 5 |
| Top Navigation Errors | Possible Frustration | 758 |
| Top Navigation Errors | Rage Click | 212 |
| Top Navigation Errors | Disabled Input Clicked | 168 |

The values are dynamic because `last_7_days` ends at the latest complete Quantum hour.
