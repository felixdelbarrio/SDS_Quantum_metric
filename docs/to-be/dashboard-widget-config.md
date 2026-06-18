# Configuracion dashboard-widget

## Pais por defecto

La UI conserva el campo publico `enabled`, pero desde Iteracion 8 significa default unico. Todos los paises configurados son elegibles para ingesta; solo uno queda marcado como default para abrir la app.

## Test pais

Cada pais tiene accion `Test pais`, que usa base URL, sesion/cookie y el endpoint local de test contra la config de ese pais.

## Dashboards y widgets

La pantalla muestra una seccion Dashboards y widgets por pais. La estructura visible representa los roles ingestables obligatorios:

- resumen: page views, sessions, converted sessions, avg session duration, detail table;
- errores: evolution, top errors, app comparison, app percentage table.

El siguiente paso natural es persistir enablement por widget en modelos dedicados; la Iteracion 8 deja la superficie UX y default country listos sin exponer secretos.
