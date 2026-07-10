# Iteración 18 — baseline técnico

Fecha: 2026-07-10. Rama base: `origin/develop`. Rama de trabajo: `feature/iteration-18-exact-widget-contracts`.

## Preflight

- El árbol estaba limpio y el trabajo previo de la rama `codex/fix-co-dashboard-parity` ya estaba integrado en `develop` mediante PR #42.
- `git fetch --all --prune` terminó correctamente.
- El target válido es `make CI`; `make ci` no existe.

## Resultado inicial

- `make CI`: PASS. Ruff, mypy, 148 pruebas backend, 37 pruebas frontend, formato, lint, typecheck, build frontend, Bandit, smoke desktop y CodeQL pasaron.
- `make build`: PASS. Se generó frontend, aplicación macOS con PyInstaller y smoke del paquete.
- Fallos preexistentes: ninguno en la automatización local.

## Huecos que el baseline no detectaba

Las pruebas aceptaban media/suma de filas, escala porcentual por magnitud, `line` forzado, labels Mobile/Desktop, correlación TABLE por orden, cabeceras inferidas y fecha mexicana. También validaban datasets legacy como fuente de Home. Por tanto, el baseline verde no demostraba paridad con Quantum Web.
