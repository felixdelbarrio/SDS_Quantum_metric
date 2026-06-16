# Regression Runbook

## Ejecutar

```bash
. .venv/bin/activate
python -m backend.app.quantum_dashboard.regression --country MX
```

Tambien puede ejecutarse desde Datasets con `Ejecutar regresion`.

## Reportes

- `docs/regression/latest-web-vs-local.md`
- `docs/regression/latest-web-vs-local.json`
- `data/parquet/country={country}/regression/web_vs_local_results/`
- `data/parquet/country={country}/regression/discrepancies/`

## Interpretacion

La regresion falla si:

- falta una card obligatoria;
- falta dataset derivado;
- falta `chart_payload` en una card grafica;
- faltan ejes, leyenda, series o puntos;
- una tabla pierde hijos expandibles;
- valores principales difieren por encima de tolerancia.

Los estados especificos ayudan a localizar el contrato roto: `failed_axis_mismatch`, `failed_legend_mismatch`, `failed_series_shape_mismatch`, `failed_expandable_rows_mismatch` y equivalentes.
