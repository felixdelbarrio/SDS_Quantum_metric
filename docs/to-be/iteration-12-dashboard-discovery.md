# Iteracion 12 - Dashboard discovery por geografia

Estado objetivo implementado:

- La configuracion ya no usa `+ Dashboard manual` como flujo principal.
- Los dashboards se refrescan por pais con `POST /api/quantum/dashboards/refresh`.
- La lista cacheada se consulta con `GET /api/quantum/dashboards?country=MX`.
- La estructura del dashboard seleccionado se refresca con `POST /api/quantum/dashboards/structure`.
- Si Quantum Web no devuelve payloads de dashboards, la API solo devuelve cache local marcada como `config_cache`.
- No se persisten cookies, Authorization ni cabeceras sensibles.

La cache vive en `config/quantum_config.json` dentro de cada pais, bajo `countries[].dashboards[]`.
