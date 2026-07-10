# Iteration 17 Dashboard Driven Architecture

La arquitectura objetivo es dashboard-driven:

1. Configuracion guarda el dashboard default por pais con tabs y widgets reales.
2. Discovery resuelve `dashboard_id`, `team_id` y lista de tabs.
3. Capture recorre esas tabs, no nombres fijos.
4. Builder transforma RAW en datasets genericos por dashboard/tab/widget.
5. API local expone el dashboard completo desde Parquet.
6. Home renderiza exactamente las tabs y widgets recibidos.
7. Regression compara Web vs Local por `dashboard_id`, `range_key`, rol y widget.

## Principios

- El catalogo especifico MX sigue existiendo para roles conocidos, pero no gobierna dashboards personalizados.
- Los widgets `generic.*` son ciudadanos de primera clase y se comparan/renderizan desde su payload.
- `tab_name` es display; `tab_index` y `tab` son claves operativas.
- Ningun dashboard debe depender de que existan tabs llamadas `Resumen` o `Errores`.
- Una ingesta no termina `completed` si falta cobertura del rango solicitado.

## Contrato de salida principal

`GET /api/local-dashboard/dashboard` devuelve:

```json
{
  "status": "ok",
  "country": "CO",
  "dashboard_id": "fccfa9f6-5d01-47cf-9ba6-b7bccd4d4f2b",
  "dashboard_name": "SDS",
  "range_key": "last_7_days",
  "tabs": [
    {
      "tab": "overview general",
      "tab_name": "Overview general",
      "tab_index": 0,
      "widgets": []
    }
  ]
}
```

## Compatibilidad

Los endpoints legacy `/summary`, `/errors` y sus tablas siguen disponibles para regresiones y herramientas antiguas. Home no los necesita para pintar el dashboard principal.
