# Runbook configuracion

1. Abrir Quantum.
2. Seleccionar browser y modo de sesion.
3. Configurar paises y Base URL.
4. Marcar un unico default.
5. Ejecutar `Test pais` en cada pais operativo.
6. Revisar Dashboards y widgets.
7. Guardar.

La seccion Browser/Sesion no contiene Pais activo. El default se gestiona en la tabla de paises.

## Iteracion 9

- La configuracion se guarda en `config/quantum_config.json`.
- El guardado es atomico y tiene `schema_version`.
- El tema `light`, `dark` o `system` persiste al reiniciar.
- Cada pais puede tener varios dashboards.
- El dashboard default descubierto no permite editar ID.
- Un dashboard manual permite editar ID hasta validarlo.
- Cada widget muestra role/ID, tipo y checkbox enabled.
- Deshabilitar un widget evita ingesta, visualizacion y regresion para ese role.
- Cookies, Authorization y tokens no se escriben en disco.
