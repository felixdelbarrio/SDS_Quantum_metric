# Desktop Packaging

## Rutas

El backend no usa rutas relativas para datos de usuario. `backend/app/config/paths.py` centraliza:

- `default_user_data_dir()`
- `default_user_log_dir()`
- `frontend_dist_path()`
- `app_bundle_root()`

En modo empaquetado se resuelve `_MEIPASS`. En desarrollo se usa el repo.

## Smoke

`scripts/smoke_test_desktop.py` valida:

- `frontend/dist/index.html` existe.
- `/api/health` responde.
- `/` sirve HTML compilado.
- El HTML no referencia Vite, `.venv` ni rutas locales de desarrollo.
- La ruta de datos por defecto no es `./data`.

`scripts/build_desktop.py` ejecuta el smoke antes de PyInstaller para fallar temprano.
