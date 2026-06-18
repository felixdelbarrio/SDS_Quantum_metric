# Iteracion 8 product finish

## Alcance

Esta iteracion cierra la app local como producto operativo: Dashboard sin KPIs duplicados, graficas con periodo/ejes legibles, ingesta diaria, cobertura de dias faltantes, configuracion por pais/dashboard/widget y Datasets centrado en persistencia auditable.

## Cambios de producto

- Home elimina calls, filas, cards, passed y Actualizar.
- Home refresca por keys de TanStack Query al cambiar pais, fecha, dimension o segmento.
- Home consulta cobertura diaria y ofrece ingesta async de dias faltantes.
- Widgets reciben `period.label` y `chart_payload.period_label` desde backend.
- Ejes X/Y salen de `chart_axes.py` con maximo razonable de labels.
- `QuantumChart` permite hover/focus, tooltip, leyenda, CSV, SVG y PNG.
- La tabla de detalle preserva o reconstruye jerarquia App Name > Sistema Operativo sin duplicar padres.
- Ingesta muestra una card activa y un historico tabular.
- Configuracion elimina Pais activo de Browser/Sesion y usa default unico por pais.
- Datasets elimina acciones tecnicas y KPIs de dashboard.

## Datos

Todos los datos mostrados por Dashboard y Datasets salen de Parquet. La ingesta es la unica zona que llama a Quantum Web.

## Validacion

La validacion automatica cubre period labels, ejes, coverage, missing-days, import/export config, parser jerarquico y UI de Home.
