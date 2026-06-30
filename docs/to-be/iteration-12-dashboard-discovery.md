# Iteracion 12 - Dashboard discovery por geografia

Estado objetivo implementado:

- La configuracion ya no usa `+ Dashboard manual` como flujo principal.
- Los dashboards se refrescan por pais con `POST /api/quantum/countries/{country}/dashboards/discover`.
- La lista cacheada se consulta con `GET /api/quantum/countries/{country}/dashboards`.
- La estructura del dashboard seleccionado se refresca con `POST /api/quantum/countries/{country}/dashboards/{dashboard_id}/structure/discover`.
- Si Quantum Web no devuelve payloads de dashboards, la API solo devuelve cache local marcada como `config_cache`.
- No se persisten cookies, Authorization ni cabeceras sensibles.

La cache vive en `config/quantum_config.json` dentro de cada pais, bajo `countries[].dashboards[]`.
