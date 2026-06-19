# Iteracion 10 - Resumen final de regresion

## Alcance

- Today.
- Yesterday.
- Last 7 Days.
- Export operativo a Downloads.
- Configuracion sin pantalla en blanco.
- Modo de sesion controlado por defecto.
- Endpoints locales con `range_key`.

## Evidencia esperada

| Rango | Reporte | Estado |
|---|---|---|
| Today | `docs/regression/today-web-vs-local.md` | PASSED |
| Yesterday | `docs/regression/yesterday-web-vs-local.md` | PASSED |
| Last 7 Days | `docs/regression/last-7-days-web-vs-local.md` | PASSED |

## Checks locales

```bash
make clean
make setup
make CI
make build
```

## Resultado local

| Check | Resultado |
|---|---|
| `make clean` | PASSED |
| `make setup` | PASSED |
| `make CI` | PASSED |
| `make build` | PASSED |
| Configuracion local | PASSED: renderiza sin pantalla en blanco, sin overlay Vite. |
| Export a Downloads | PASSED: ZIP creado en `~/Downloads`. |
| Today local status | PASSED: 9/9 cards, regresion `PASSED`. |
| Ingesta sin respuestas Quantum | PASSED: falla explicitamente, no publica falso `completed`. |

## Nota operativa

La verificacion runtime con sesion `controlled` no autenticada no recibio responses `/analytics`
desde Quantum. El flujo queda protegido: la ingesta termina `failed` con mensaje accionable en vez
de reutilizar datos previos o quedarse en curso.

