# Contrato gráfico Iteración 18

El contrato admite `line`, `bar`, `area`, `stacked_bar`, `donut` y `mixed`; las series admiten `line`, `bar`, `area`, `baseline`, `band` y `anomaly`. Conserva id, label, kind, order, visibility, puntos, ejes, ticks, leyendas, bandas, periodo, timezone y granularidad.

React dibuja barras con `rect`, baseline discontinua, áreas cerradas y anomaly con patrón SVG/tokens CSS. Las bandas solo se ubican mediante posiciones explícitas o coincidencia exacta con ticks; no se asigna una posición por índice. El caption usa literalmente `period_label`.
