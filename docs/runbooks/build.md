# Build Runbook

## Entorno

```bash
make clean
make setup
```

`make setup` instala dependencias backend, desktop y frontend.

## CI local

```bash
make CI
```

Ejecuta formato, lint, mypy, pytest, typecheck, tests frontend, build Vite, smoke desktop preflight y CodeQL local.

## Binario

```bash
make build
```

Construye frontend, valida smoke desktop y ejecuta PyInstaller. El binario usa ruta persistente de usuario para Parquet y logs.
