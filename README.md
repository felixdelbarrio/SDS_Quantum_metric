# SDS Quantum Metric

Aplicacion local para ingerir datos reales de Quantum Metric, guardarlos en Parquet por pais y visualizarlos offline mediante APIs locales.

[![CI develop](https://github.com/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/actions/workflows/ci.yml)
[![CI master](https://github.com/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/actions/workflows/ci.yml)

## Comandos

```bash
make setup
make run
make CI
make build
make kill
```

`make run` levanta backend FastAPI, frontend Vite y un visor desktop PyWebView. Las pantallas principales consumen solo APIs locales respaldadas por Parquet; Quantum se llama exclusivamente desde Test de conexion e Ingesta.

## Seguridad

Las cookies de Quantum se leen solo bajo demanda, se mantienen en memoria y no se persisten. El modo manual tambien mantiene la cookie solo en memoria.

## Estado

- As-Is documentado en `docs/as-is`.
- Backend local versionado bajo `/api`.
- Persistencia Parquet en `data/parquet/country=<pais>`.
- Export/import ZIP en `data/exports`.
