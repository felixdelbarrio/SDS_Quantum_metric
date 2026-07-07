# Runbook - Configuracion

1. Abrir Configuracion.
2. Elegir pais y Base URL.
3. Usar `Actualizar dashboards`.
4. Confirmar que el combo muestra nombres y que el valor interno es el dashboard ID.
5. Seleccionar el dashboard real en el combo.
6. Usar `Anadir dashboard manual` si el dashboard no viene de la API.
7. Validar el dashboard manual antes de marcarlo como default.
8. Verificar que `Default del pais` esta marcado.
9. Usar `Validar dashboard` si se necesita refrescar tabs/widgets.
10. Guardar.

Si no hay default, la aplicacion no permite guardar.

La lista de dashboards se cachea en `config/dashboard_resources/<country>.json`.
`Actualizar dashboards` fuerza una nueva llamada GraphQL `resourcesList`; abrir Configuracion usa cache/config local.

Desde Iteracion 15:

- `Test pais`, `Actualizar dashboards` y `Validar dashboard` muestran pending, success y error.
- Colombia puede usar manualmente `https://bbvaco.quantummetric.com` y el dashboard SDS.
- El selector usa `dashboard_id` como value y `name` como label.

Desde Iteracion 16:

- CHART/KPI, TABLE y DONUT desconocidos se evalúan por capacidad y dejan de aparecer como `no soportado` si existe parser generico.
- Colombia SDS debe quedar con 11 widgets habilitados/soportados.
- Si un dashboard manual comparte `card_id` entre widgets TABLE, la validacion conserva el orden de widgets de Quantum para resolverlos.
