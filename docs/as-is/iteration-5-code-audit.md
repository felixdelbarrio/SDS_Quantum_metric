# Iteracion 5 Code Audit

## Findings

1. Codigo muerto: `MiniTimeseries` dibujaba curvas locales simplificadas y quedo eliminado.
2. Parsers debiles: los parsers aceptaban aliases genericos y permitian valores agregados sin contrato grafico. Ahora el valor puede persistirse, pero la grafica exige `chart_payload`.
3. Derivados incompletos: faltaba una entidad auditable para payloads graficos. Se agrega `derived/chart_payloads`.
4. Campos perdidos: ejes, leyendas, bandas y periodo no viajaban como contrato estructurado entre RAW, derivados y UI.
5. Calculos duplicados: la UI renderizaba escalas desde `timeseries`; ahora las escalas vienen del payload backend.
6. Curvas aproximadas: `MiniTimeseries` normalizaba min/max localmente y no tenia Mobile/Desktop ni ejes.
7. Estilos dispersos: se agregan tokens de chart, dashboard y semantica; los componentes nuevos usan clases globales.
8. Performance: Datasets no paginaba por entidad y podia crecer mal con historicos largos. Se agregan endpoints de entidad paginados.
9. Pendiente Web: la exactitud total depende de que Quantum entregue ejes, bandas y series por dispositivo en RAW. Si faltan, regresion marca contrato incompleto.
10. Excluido: videos de sesiones. Local no implementa reproduccion, descarga, cache, rutas ni enlaces de video.

## Canonical Route

RAW Quantum -> Visual Contract -> Derived Parquet -> Local API -> React UI -> Regression Report.

Las rutas `analytics/*` quedan como compatibilidad, pero Home usa `local-dashboard/*` y datasets derivados.
