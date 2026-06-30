# Configuracion De Dashboard Default

Reglas activas:

- Cada pais activo debe tener exactamente un dashboard default para guardar.
- El backend rechaza guardado sin default validado.
- El frontend bloquea `Guardar` y muestra el pais pendiente.
- El selector muestra el dashboard default al entrar.
- Cambiar el selector marca ese dashboard como default y refresca estructura bajo demanda.

Los campos `Dashboard ID`, `Nombre`, `Tipo` y `Team ID` se muestran como lectura para dashboards descubiertos.
