# Generic Dashboard Rendering

Home renderiza widgets desde `derived/dashboard_widgets`.

## Widgets soportados

| Tipo | Render |
|---|---|
| CHART/KPI | Card KPI con valor, delta y `chart_payload` si existe |
| TABLE | Tabla generica con columnas/filas persistidas |
| DONUT | Card con payload donut y detalle |

## Reglas UX

- No se fabrican tabs.
- No se muestran dumps tecnicos de roles faltantes.
- Una tabla generica no necesita endpoints especificos de detalle para aparecer en Home.
- El dominio visible de una card usa `tab_name`; si falta, cae al fallback legacy.

## Datos

Cada widget local conserva:

- `dashboard_id`
- `dashboard_name`
- `card_role`
- `widget_id`
- `tab`
- `tab_name`
- `tab_index`
- `chart_payload` o `table_rows`
