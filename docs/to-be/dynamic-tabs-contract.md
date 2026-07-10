# Dynamic Tabs Contract

Las tabs salen de Quantum/configuracion y viajan por todo el pipeline.

## Campos

| Campo | Uso |
|---|---|
| `tab_index` | Orden y URL `tab=<index>` de Quantum |
| `tab` | Token operativo estable o normalizado |
| `tab_name` | Nombre visible en Home |
| `tab_id` | ID de Quantum cuando esta disponible |

## Reglas

- Capture usa todas las tabs configuradas y solo falla si todas quedan sin analytics.
- Si una tab no tiene widgets locales, se muestra vacia pero no se reemplaza por tabs default.
- El agrupado local usa `tab_index` para evitar duplicados por nombres legacy distintos.
- `Resumen` y `Errores` solo aparecen si son tabs reales/configuradas del dashboard.

## Caso validado

CO/SDS:

- `Overview general` (`tab_index=0`)
- `Easy Dashboard Example` (`tab_index=1`)

MX default mantiene sus tabs configuradas legacy sin contaminar CO.
