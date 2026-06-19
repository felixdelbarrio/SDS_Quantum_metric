from __future__ import annotations

import logging
import threading
import time
import urllib.request
from typing import Any

import uvicorn

from backend.app.config.paths import default_user_log_dir
from backend.app.config.settings import get_settings
from backend.app.main import app
from desktop.backend_runtime import (
    is_compatible_health,
    next_available_port,
    port_available,
    read_health,
)
from desktop.icon import apply_macos_app_icon, resolve_icon_png


def main() -> None:
    settings = get_settings()
    log_path = _configure_logging()
    port = settings.backend_port
    url = f"http://{settings.backend_host}:{port}"
    server: uvicorn.Server | None = None
    thread: threading.Thread | None = None
    try:
        health = read_health(url + "/api/health")
        if is_compatible_health(health):
            logging.info("Reusing compatible SDS Quantum Metric backend at %s", url)
        else:
            if health is not None:
                port = next_available_port(settings.backend_host, settings.backend_port + 1)
                logging.warning(
                    "Ignoring incompatible backend on configured port %s; using %s instead.",
                    settings.backend_port,
                    port,
                )
            elif not port_available(settings.backend_host, port):
                port = next_available_port(settings.backend_host, settings.backend_port + 1)
                logging.warning(
                    "Configured port %s is busy; using %s instead.",
                    settings.backend_port,
                    port,
                )
            url = f"http://{settings.backend_host}:{port}"
            server = uvicorn.Server(
                uvicorn.Config(
                    app,
                    host=settings.backend_host,
                    port=port,
                    log_level="info",
                )
            )
            thread = threading.Thread(target=server.run, name="sds-uvicorn", daemon=False)
            thread.start()
            _wait_for(url + "/api/health")
        _wait_for(url + "/")
        import webview

        apply_macos_app_icon()
        _create_window(webview, url)
        webview.start()
    except Exception as exc:
        logging.exception("SDS Quantum Metric failed to start")
        _show_error(exc, log_path, url)
        if server is not None:
            try:
                server.should_exit = True
                if thread and thread.is_alive():
                    thread.join(timeout=5)
            except Exception:
                logging.exception("Failed to stop embedded server")
    finally:
        if server is not None:
            server.should_exit = True


def _wait_for(url: str) -> None:
    deadline = time.time() + 45
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url}")


def _create_window(webview: Any, url: str) -> object:
    kwargs: dict[str, object] = {"width": 1320, "height": 900}
    icon = _window_icon()
    if icon:
        kwargs["icon"] = icon
    try:
        return webview.create_window("SDS Quantum Metric", url, **kwargs)
    except TypeError as exc:
        if "icon" not in kwargs or "icon" not in str(exc):
            raise
        kwargs.pop("icon")
        return webview.create_window("SDS Quantum Metric", url, **kwargs)


def _window_icon() -> str | None:
    return resolve_icon_png()


def _configure_logging() -> str:
    log_dir = default_user_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "desktop.log"
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.info("Starting SDS Quantum Metric desktop shell")
    return str(log_path)


def _show_error(exc: Exception, log_path: str, url: str) -> None:
    message = (
        "SDS Quantum Metric no pudo abrirse.\n\n"
        f"URL local: {url}\n"
        f"Detalle: {exc}\n\n"
        f"Log: {log_path}"
    )
    try:
        import webview

        webview.create_window("SDS Quantum Metric - Error", html=f"<pre>{message}</pre>")
        webview.start()
    except Exception:
        print(message)


if __name__ == "__main__":
    main()
