# Dashboard Discovery Contract

`QuantumDashboardSummary`:

- `dashboard_id`: identificador real de Quantum.
- `name`: nombre real mostrado por Quantum Web.
- `type`: tipo recibido del payload.
- `team_id`: team asociado cuando Quantum lo devuelve.
- `country`: geografia local.
- `source`: `quantum_api`, `quantum_web` o `config_cache`.
- `discovered_at`: timestamp UTC.

Reglas:

- Se deduplica por `dashboard_id`.
- Gana la fuente Web/API frente a cache.
- La cache solo es fallback explicito.
- Los payloads se parsean de forma defensiva y no guardan material de sesion.
