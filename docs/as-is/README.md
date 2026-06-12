# Quantum Metric As-Is

Fecha de levantamiento: 2026-06-12.

Este levantamiento se hizo contra `https://bbvamx.quantummetric.com/` usando la sesion existente de Chrome bajo demanda. Las cookies se descifraron solo en memoria desde Chrome/Keychain, se inyectaron en un contexto Playwright no persistente y no se escribieron valores de cookie, tokens ni payloads sensibles en disco.

## Evidencia de conectividad autenticada

- Chrome tenia abierta la ruta `/#/dashboard/8e53eb82-587c-4b92-a0fa-0f6283677e28?tab=0&teamID=1da677de-9313-4b49-9110-81a6b756ca7e`.
- Se detectaron cookies para `bbvamx.quantummetric.com`, `.bbvamx.quantummetric.com`, `.quantummetric.com` e `.iam.quantummetric.com`; solo se registraron nombres y conteos.
- `GET /data/init`: HTTP 200, JSON parseable, incluye `isUserAuthenticated` y `qmServicesEndpoint`.
- `GET /auth-token`: HTTP 200, JSON parseable, devuelve token de acceso en memoria.
- `POST https://api.quantummetric.com/query`: HTTP 200 con `query { permissions { id handle accessLevel } }`, devolvio 76 permisos.
- `POST /analytics`: HTTP 200, respuestas JSON con claves `id`, `metadata`, `namespace`, `processed`, `project`, `rows`, `stats`.
- `POST /analytics/historical`: HTTP 200, respuestas JSON con datos historicos para cards del dashboard.

## Alcance cubierto

- Portal base y bootstrap.
- Modelo de sesion IAM + token.
- Dashboard `Dashboard General MX`.
- Tabs visibles: `Resumen` y `Errores`.
- Cards visibles en el primer tab y llamadas de analytics asociadas.
- Endpoints de configuracion, GraphQL, analytics e historicos.

## Limites del levantamiento

- No se ejecutaron mutaciones ni acciones destructivas.
- No se inspeccionaron todos los dashboards de la cuenta; se valido el dashboard abierto por el usuario.
- No se persistieron HAR ni trazas completas para evitar filtrado accidental de datos.
- El inventario de bodies esta anonimizado por estructura; los bodies completos deben capturarse en memoria durante la ingesta real.

## Decision para To-Be

La aplicacion local debe implementar la ingesta capturando llamadas reales de `POST /analytics` y `POST /analytics/historical` durante una navegacion autenticada efimera, persistiendo request/response sanitizados y datos tabulares derivados en Parquet. El test de conexion puede usar `GET /data/init`, `GET /auth-token` y `POST /query` como prueba rapida y no destructiva.
