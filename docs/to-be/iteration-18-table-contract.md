# Contrato de tablas Iteración 18

Cada columna incluye key, label exacto, tipo, precisión, sortable y default sort. La tabla conserva filas, orden por defecto, periodo y timezone.

El frontend no inspecciona el título ni convierte `metric_1` en una etiqueta. Las TABLE genéricas sin cabeceras explícitas fallan con `failed_missing_table_contract`. Dos TABLE con el mismo card id fallan por correlación ambigua en vez de intercambiar filas.
