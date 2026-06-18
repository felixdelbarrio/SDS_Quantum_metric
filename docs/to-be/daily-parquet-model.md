# Modelo Parquet diario

## Canonico

La ingesta materializa raw calls en:

```text
parquet/country=MX/day=YYYY-MM-DD/raw_api_calls/raw_api_calls.parquet
parquet/country=MX/manifests/day_coverage.parquet
```

El dataset compacto legacy `parquet/country=MX/raw_api_calls/raw_api_calls.parquet` se conserva como artefacto de migracion y compatibilidad interna, pero las lecturas de cobertura prefieren particiones diarias.

## Cobertura

`day_coverage.parquet` contiene:

- `country`
- `day`
- `status`
- `raw_calls`
- `source_start`
- `source_end`
- `updated_at`

Si el manifest no existe, el store calcula cobertura desde `source_ts_start/source_ts_end`.

## Rangos

- Today lee el dia local Mexico.
- Yesterday lee el dia local anterior.
- Last 7 Days lee siete particiones inclusivas.
- Custom lee todos los dias entre start y end.

Los limites se calculan en `America/Mexico_City` para evitar desplazar dias por UTC.
