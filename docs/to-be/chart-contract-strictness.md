# Chart Contract Strictness

## Regla

Las graficas locales se pintan solo desde `chart_payload` persistido. React no fabrica curvas, ejes ni series desde agregados.

## Fallos

Si una card grafica obligatoria no trae payload valido, el builder conserva raw/contracts/snapshots para auditoria, no sobrescribe derivados validos y marca `failed_missing_chart_payload`.

La regresion tambien falla con estados especificos para periodo, tiempo, widget, porcentaje, ejes, leyenda y series.

## UI

Home muestra `Fallo contractual de grafica local` para indicar que hay que regenerar derivados, ejecutar regresion o relanzar ingesta.
