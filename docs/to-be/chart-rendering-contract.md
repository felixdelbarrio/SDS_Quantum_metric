# Chart Rendering Contract

## Datos

El backend persiste `chart_payload` con ejes, ticks, series, puntos, bandas, leyenda, periodo y `chart_type`. El frontend no fabrica puntos ni reescala datos fuera del contrato SVG.

## Modos

- `line`: renderiza una curva SVG `path` suavizada cuando hay tres o mas puntos.
- `bar`: renderiza barras SVG `rect` por punto y serie. No hay `path` principal de linea.
- `donut`: renderiza segmentos desde los puntos persistidos y muestra valor + porcentaje.

## Interacciones

Tooltips, foco de teclado, CSV, SVG y PNG usan el mismo payload. Cambiar Linea/Barras solo cambia representacion visual; no modifica valores, ejes ni periodo.

## Fallo contractual

Si falta `chart_payload`, la UI muestra fallo contractual y la regresion debe fallar. No se renderizan datos de ejemplo.
