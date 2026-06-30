# Dashboard List API Contract

## Endpoint

`GET /api/quantum/countries/{country}/dashboards`

Devuelve la cache local auditable para el pais.

`POST /api/quantum/countries/{country}/dashboards/discover`

Abre Quantum Web con la sesion configurada, captura contexto autenticado de `POST /query` y ejecuta `resourcesList` con filtro `DASHBOARD`.

## Respuesta

```json
{
  "country": "MX",
  "source": "quantum_web",
  "dashboards": [
    {
      "dashboard_id": "8e53eb82-587c-4b92-a0fa-0f6283677e28",
      "name": "Dashboard General MX",
      "type": "DASHBOARD",
      "team_id": "1da677de-9313-4b49-9110-81a6b756ca7e",
      "country": "MX",
      "order": 0,
      "is_default_candidate": false,
      "source": "quantum_web",
      "discovered_at": "2026-06-30T00:00:00Z"
    }
  ],
  "warning": null
}
```

## Reglas

- `dashboard_id` es siempre el id real de Quantum.
- `name` es el nombre real mostrado por Quantum.
- `order` respeta el orden recibido de `resourcesList`.
- Si Quantum no devuelve `team_id`, se preserva el `team_id` configurado previamente para el pais o dashboard.
- No se crea ningun dashboard manual ni default ficticio.
