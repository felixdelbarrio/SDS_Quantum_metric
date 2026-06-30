# Iteracion 13 - Fix de descubrimiento real

Estado objetivo implementado:

- La lista de dashboards se obtiene desde GraphQL `resourcesList` sobre `POST https://api.quantummetric.com/query`.
- La estructura del dashboard se obtiene desde GraphQL `LoadDashboard($dashboardId: ID!)`.
- La API local expone rutas por pais:
  - `GET /api/quantum/countries/{country}/dashboards`
  - `POST /api/quantum/countries/{country}/dashboards/discover`
  - `POST /api/quantum/countries/{country}/dashboards/{dashboard_id}/structure/discover`
- `QuantumDashboardSummary` conserva `dashboard_id`, `name`, `type`, `team_id`, `country`, `order`, `is_default_candidate`, `source` y `discovered_at`.
- `QuantumDashboardStructure` conserva `dashboard_name`, tabs reales y widgets reales. Un widget de card `CHART` con `visualization=donut` se clasifica como `donut`.
- La configuracion no crea widgets por defecto. Un dashboard sin estructura queda vacio.
- El selector frontend muestra nombres reales y usa `dashboard_id` como value. Si no hay default, queda en placeholder y no permite guardar.
- La ingesta solo usa el dashboard default del pais y sus widgets soportados/habilitados.

## Seguridad y rendimiento

- Las cookies y cabeceras `Authorization` solo viven durante la captura Playwright o la llamada GraphQL directa asociada al contexto.
- No se persisten payloads con secretos.
- El parser trabaja sobre la respuesta concreta `resourcesList`/`LoadDashboard` antes de usar recorrido defensivo, evitando escaneos amplios.
- La deduplicacion conserva el orden de Quantum y no ordena alfabeticamente.
