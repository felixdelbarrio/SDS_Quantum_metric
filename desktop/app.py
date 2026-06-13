from __future__ import annotations

import threading
import time
import urllib.request
from typing import Any

import uvicorn

from backend.app.config.settings import get_settings
from backend.app.main import app
from desktop.icon import apply_macos_app_icon, resolve_icon_png


def main() -> None:
    settings = get_settings()
    url = f"http://{settings.backend_host}:{settings.backend_port}"
    server = uvicorn.Server(
        uvicorn.Config(
            app, host=settings.backend_host, port=settings.backend_port, log_level="info"
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_for(url + "/api/health")
    try:
        import webview

        apply_macos_app_icon()
        _create_window(webview, url)
        webview.start()
    except Exception:
        print(f"SDS Quantum Metric: {url}")
        try:
            while thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
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


if __name__ == "__main__":
    main()
