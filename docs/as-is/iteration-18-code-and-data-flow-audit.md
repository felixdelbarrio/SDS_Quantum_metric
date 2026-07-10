# Iteración 18 — auditoría de código y flujo de datos

## Primera divergencia

La primera divergencia ocurría en RAW → parser: cuando faltaba un valor visible, `parsers.py` agregaba filas y convertía porcentajes. Después `builder.py` volvía a combinar llamadas, recalculaba el valor y fabricaba series/labels. El frontend añadía una tercera reinterpretación mediante formato global, cabeceras por título y fecha de México.

## Hallazgos confirmados

| Capa | Hallazgo as-is | Corrección |
|---|---|---|
| `generic_roles.py` | tab desconocida terminaba en Summary | resolución `resolved/unassigned/ambiguous`; nunca por título |
| `widget_roles.py` | TABLE duplicadas se asignaban por secuencia | no hay round-robin; la ambigüedad falla |
| `parsers.py` | suma/media, `_as_percent`, `line` y labels implícitos | resolutores explícitos y estados missing/ambiguous/invalid |
| `builder.py` | recomputaba totales y Mobile/Desktop | no modifica el valor; solo adjunta un gráfico explícito único |
| `dashboard_structure.py` | perdía sección y dimensiones | conserva section id/name/index y x/y/width/height |
| `service.py` | Home podía caer a `dashboard_widgets`/datasets semánticos | Home lee solo `derived/widget_contracts` |
| ingesta/rangos | CST/México era default transversal | timezone país/dashboard se propaga a rango, captura y coverage |
| `HomePage.tsx` | grid plano por tab y `todayInMexico` | Tab → Section → grid; timezone configurada |
| `KpiWidget.tsx` | precisión global y headers por título | `QuantumFormattedValue` y columnas contractuales |
| charts | periodo regenerado y ticks convertidos | labels/ticks/periodo literales; bar/area/baseline/band/anomaly |

## Archivos auditados

Se revisaron todos los ficheros backend/frontend enumerados en el alcance, incluyendo discovery/config, normalizer/query engine, evidence/regression, Datasets y QuantumPage. `regression.py` y los endpoints Summary/Errors aún consumen vistas legacy para compatibilidad funcional; ya no compiten como fuente de Home. Deben retirarse en una iteración posterior solo cuando sus consumidores públicos hayan migrado.

## Datos locales encontrados

La persistencia local/configuración rastreada contiene México y el dashboard `8e53eb82-587c-4b92-a0fa-0f6283677e28`; no existe un corpus CO canónico suficiente para reproducir SDS. No se fabricaron datos CO ni contratos de producción.
