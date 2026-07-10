# Migración de almacenamiento Iteración 18

Dataset canónico: `country=<country>/range_key=<range>/derived/widget_contracts`.

La partición lógica contiene country, dashboard id, range key, tab id, section id y widget id. Home y `/api/local-dashboard/dashboard` no caen a `derived/dashboard_widgets`, Summary o Errors. Schema de configuración sube a 3.

Los Parquet anteriores no se reinterpretan como schema 3: se requiere una nueva ingesta. Los datasets semánticos existentes quedan temporalmente como vistas para endpoints legacy, nunca como fuentes competidoras de Home. Su eliminación requiere migrar primero esos endpoints y clientes.
