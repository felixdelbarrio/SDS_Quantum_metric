from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from backend.app.config.settings import Settings

LOGGER = logging.getLogger(__name__)
ANALYTICS_PATHS = {"/analytics", "/analytics/historical"}


class ControlledSessionError(RuntimeError):
    pass


def launch_controlled_context(
    playwright: Any,
    settings: Settings,
    *,
    headless: bool,
) -> Any:
    profile = settings.runtime_dir / "quantum-controlled-profile"
    profile.mkdir(parents=True, exist_ok=True)
    executable = _chrome_executable(settings)
    if not headless and executable is None:
        raise ControlledSessionError(
            "Chrome no esta disponible para autenticar la sesion gestionada."
        )
    options: dict[str, Any] = {
        "headless": headless,
        "ignore_https_errors": not settings.qm_verify_tls,
        "args": ["--disable-dev-shm-usage", "--no-first-run"],
    }
    if executable is not None:
        options["executable_path"] = str(executable)
    try:
        return playwright.chromium.launch_persistent_context(str(profile), **options)
    except Exception as exc:
        LOGGER.exception("Could not launch the managed Quantum browser profile.")
        raise ControlledSessionError(
            "No se pudo abrir la sesion gestionada de Quantum. "
            "Cierra cualquier ventana de autenticacion anterior y vuelve a intentarlo."
        ) from exc


def invalidate_controlled_quantum_cache(
    context: Any,
    page: Any,
    *,
    base_url: str,
) -> None:
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if not parsed.scheme or not parsed.netloc:
        raise ControlledSessionError("La URL base de Quantum no es valida.")
    try:
        session = context.new_cdp_session(page)
        session.send(
            "Storage.clearDataForOrigin",
            {
                "origin": origin,
                "storageTypes": "service_workers,cache_storage,indexeddb",
            },
        )
        session.send("Network.enable")
        session.send("Network.setCacheDisabled", {"cacheDisabled": True})
    except Exception as exc:
        LOGGER.exception("Could not invalidate the managed Quantum data cache.")
        raise ControlledSessionError("No se pudo preparar una captura fresca de Quantum.") from exc


def authenticate_controlled_session(
    settings: Settings,
    *,
    base_url: str,
    dashboard_url: str,
    timeout_seconds: int = 300,
) -> dict[str, object]:
    return _verify_controlled_session(
        settings,
        base_url=base_url,
        dashboard_url=dashboard_url,
        timeout_seconds=timeout_seconds,
        headless=False,
    )


def check_controlled_session(
    settings: Settings,
    *,
    base_url: str,
    dashboard_url: str,
    timeout_seconds: int = 60,
) -> dict[str, object]:
    return _verify_controlled_session(
        settings,
        base_url=base_url,
        dashboard_url=dashboard_url,
        timeout_seconds=timeout_seconds,
        headless=True,
    )


def _verify_controlled_session(
    settings: Settings,
    *,
    base_url: str,
    dashboard_url: str,
    timeout_seconds: int,
    headless: bool,
) -> dict[str, object]:
    expected_host = urlparse(base_url).hostname
    statuses: list[int] = []
    final_url = ""
    with sync_playwright() as playwright:
        context = launch_controlled_context(playwright, settings, headless=headless)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            invalidate_controlled_quantum_cache(
                context,
                page,
                base_url=base_url,
            )

            def on_response(response: Any) -> None:
                parsed = urlparse(response.url)
                if parsed.hostname == expected_host and parsed.path in ANALYTICS_PATHS:
                    statuses.append(int(response.status))

            page.on("response", on_response)
            page.goto(dashboard_url, wait_until="domcontentloaded", timeout=60_000)
            deadline = time.monotonic() + max(1, timeout_seconds)
            while time.monotonic() < deadline and not statuses:
                page.wait_for_timeout(500)
            final_url = page.url
        finally:
            context.close()

    successful = [status for status in statuses if 200 <= status < 400]
    if successful:
        return {
            "status": "ok",
            "message": "Sesion gestionada autenticada con datos Quantum.",
            "analytics_responses": len(statuses),
            "analytics_statuses": sorted(set(statuses)),
        }
    if _is_authentication_url(final_url):
        raise ControlledSessionError(
            "La sesion gestionada no se ha autenticado antes de agotar el tiempo disponible."
        )
    raise ControlledSessionError(
        "Quantum no emitio respuestas analytics para validar la sesion gestionada."
    )


def _chrome_executable(settings: Settings) -> Path | None:
    executable = settings.chrome_executable.expanduser()
    return executable if executable.is_file() else None


def _is_authentication_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").casefold()
    return host.startswith("idp.") or host == "iam.quantummetric.com"
