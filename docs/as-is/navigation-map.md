# Navigation Map

## Base

- Base URL: `https://bbvamx.quantummetric.com/`
- SPA hash router: rutas bajo `/#/...`
- Assets principales: `https://external.quantummetric.com/web-ui/main/assets/...`
- Servicios GraphQL: `https://api.quantummetric.com/query`

## Ruta analizada

- Dashboard: `/#/dashboard/8e53eb82-587c-4b92-a0fa-0f6283677e28`
- Team: `1da677de-9313-4b49-9110-81a6b756ca7e`
- Titulo visible: `Dashboard General MX`
- Descripcion visible: `Este dashboard es un resumen de sesiones y errores.`

## Navegacion visible

- Selector de team: `GLOMO`
- Segmento global: `All data + segment`
- Date picker global: `Today to 4:59AM CST`
- Navbar metrics: `users` y `sessions`
- Busqueda global: `Search + K`
- Acciones de dashboard: `Add Dashboard Dimension`, `Dashboard Segment`
- Tabs del dashboard:
  - `Resumen`
  - `Errores`

## Rutas internas observadas en bundles

- `/dashboard/:dashboardId`
- `/dashboards/`
- `/shared_dashboards/`
- `/sandbox/card/:cardId`
- `/dimension/event`
- `/dimension/error`
- `/dimension/geography`
- `/dimension/browser`
- `/dimension/os`
- `/dimension/platform`
- `/search`
- `/users/search`
- `/query_admin_wren`
- `/reports`
- `/alerts`
- `/live`
- `/interactions`

## Observaciones

- El dashboard usa hash routing; las llamadas de datos se hacen desde la SPA despues del bootstrap.
- Algunos links visuales de cards usan un id de ruta distinto al `metadata.cardId` que aparece en `/analytics`. La persistencia local debe conservar ambos cuando esten disponibles.
