# Iteracion 13 - Audit de descubrimiento real de dashboards

Fecha: 2026-06-30.

## Hallazgos

- Quantum Web no lista dashboards en una ruta REST con `dashboard` en el path. La llamada real observada es `POST https://api.quantummetric.com/query`.
- El listado usa GraphQL `resourcesList` con `resourceFilter.types=["DASHBOARD"]`. La respuesta valida contiene `data.resources.totalCount` y `data.resources.resources[]`.
- La estructura de un dashboard se lee con GraphQL `LoadDashboard($dashboardId: ID!)`.
- En `LoadDashboard`, `entity.tabs` llega como JSON serializado. Los widgets reales estan dentro de cada tab en `layoutCardsMap`; `entity.cards` puede venir vacio.
- Los tabs reales de `Dashboard General MX` son `Resumen` y `Errores`. El widget de donut de errores aparece como card `type=CHART` con `visualization=donut`.
- El flujo anterior buscaba respuestas JSON cuyo path/query contuviera `dashboard` o `menu`, por lo que podia no capturar la llamada real `/query`.
- El endpoint local anterior de estructura solo reserializaba cache local y el modelo sembraba widgets por defecto, mezclando secciones y creando contenido que no provenia de Quantum.
- El frontend seleccionaba el primer dashboard cuando no habia default, lo que ocultaba configuraciones incompletas.

## Riesgos

- Persistir o loguear `Authorization`/cookies invalidaria el modelo de seguridad. El nuevo flujo solo usa cabeceras de sesion en memoria.
- Usar fallback generico para widgets puede volver a mezclar tabs. La ruta preferente debe ser `LoadDashboard -> entity.tabs -> layoutCardsMap`.
- Si no hay estructura real descubierta, el dashboard debe quedar sin widgets en vez de mostrar defaults ficticios.

## Evidencia operativa

- El endpoint real de lista devuelve 18 dashboards para Mexico en la sesion validada.
- `Dashboard General MX` aparece con id `8e53eb82-587c-4b92-a0fa-0f6283677e28`.
- `LoadDashboard` para ese id devuelve `entity.title="Dashboard General MX"` y dos tabs con `layoutCardsMap`.
