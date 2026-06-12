# Security

## Principios

- Cookie y tokens solo en memoria.
- Sin cookies, tokens ni Authorization headers en logs, errores, manifests o exports.
- Lectura de cookies solo por accion explicita del usuario.
- Sanitizacion recursiva de estructuras antes de persistir.
- Export ZIP excluye configuracion y runtime.

## Browser mode

En macOS/Chrome, la app lee `~/Library/Application Support/Google/Chrome/*/Cookies` en modo read-only y usa Keychain para descifrar valores. Este proceso se ejecuta solo durante Test de conexion o Ingesta.

## Manual mode

El usuario puede pegar una cookie. El valor se guarda en un almacen de secretos en memoria y se borra al finalizar el proceso.

## Validaciones

`make CI` ejecuta `scripts/scan_no_secrets.py`, que falla si detecta patrones obvios de cookies o tokens persistidos en archivos versionados.
