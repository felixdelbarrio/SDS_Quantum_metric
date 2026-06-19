# Hardening de sesion Chrome

## Problema

El modo anterior podia leer perfiles reales de Chrome para reutilizar cookies. En entornos con
EDR, esa operacion puede disparar avisos de seguridad porque accede a artefactos sensibles del
navegador.

## Decisiones

- El modo por defecto es `controlled`.
- `controlled` usa un perfil Playwright propio bajo `runtime/quantum-controlled-profile`.
- La app no lee bases de datos ni perfiles reales de Chrome en el modo por defecto.
- Las configuraciones persistidas con `browser` migran a `controlled` al leerse.
- `browser` queda solo como compatibilidad interna legacy, no como opcion normal de UI.
- `manual` mantiene cookies solo en memoria y nunca las escribe en disco.

## Contrato operativo

| Modo | Acceso a perfil Chrome real | Persistencia de cookies | Uso recomendado |
|---|---:|---:|---|
| `controlled` | No | Perfil controlado local de la app | Default seguro. |
| `manual` | No | No | Sesiones puntuales. |
| `browser` | Si | No | Compatibilidad legacy; se migra a `controlled`. |

## Validacion

`config_store.py` migra defaults y configuraciones legacy a `controlled`. `capture.py` crea el
contexto persistente controlado sin invocar `BrowserCookieProvider`.
