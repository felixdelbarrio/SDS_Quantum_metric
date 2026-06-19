# Regression Runbook

## Ejecutar

```bash
. .venv/bin/activate
python -m backend.app.quantum_dashboard.regression --country MX
```

Tambien puede ejecutarse desde Datasets con `Ejecutar regresion`.

Para rangos no Today:

```bash
python -m backend.app.quantum_dashboard.regression --country MX --range-key yesterday
python -m backend.app.quantum_dashboard.regression --country MX --range-key last_7_days
```

## Reportes

- `docs/regression/latest-web-vs-local.md`
- `docs/regression/latest-web-vs-local.json`
- `docs/regression/today-web-vs-local.md`
- `docs/regression/yesterday-web-vs-local.md`
- `docs/regression/last-7-days-web-vs-local.md`
- `data/parquet/country={country}/regression/web_vs_local_results/`
- `data/parquet/country={country}/regression/discrepancies/`
- `data/parquet/country={country}/range_key={range}/regression/...`

## Interpretacion

La regresion falla si:

- falta una card obligatoria;
- falta dataset derivado;
- falta `chart_payload` en una card grafica;
- falta etiqueta de periodo en `chart_payload`;
- el rango temporal local no coincide con el rango capturado de Quantum Web;
- el `range_key` de los raw calls no coincide con el rango consultado;
- faltan ejes, leyenda, series o puntos;
- una tabla pierde hijos expandibles;
- valores principales difieren por encima de tolerancia.

Los estados especificos ayudan a localizar el contrato roto: `failed_missing_chart_payload`, `failed_period_label_mismatch`, `failed_time_range_mismatch`, `failed_widget_value_mismatch`, `failed_percentage_mismatch`, `failed_axis_mismatch`, `failed_legend_mismatch`, `failed_series_shape_mismatch`, `failed_expandable_rows_mismatch` y equivalentes.
# Rangos obligatorios

Validar y conservar reportes para:

- `docs/regression/today-web-vs-local.md`
- `docs/regression/yesterday-web-vs-local.md`
- `docs/regression/last-7-days-web-vs-local.md`

Cada reporte debe terminar en `PASSED`.

# Evidencia

Para investigar una discrepancia:

```bash
curl http://127.0.0.1:8765/api/datasets/MX/evidence
```

El reporte enlaza valor Web visible, hashes Quantum, RAW Parquet, derivado y valor API local. El primer punto de divergencia indica si el problema esta en parser, agregacion o API/UI local.
