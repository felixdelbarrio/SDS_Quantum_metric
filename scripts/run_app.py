from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from typing import Any

from backend.app.config.settings import get_settings
from desktop.backend_runtime import (
    is_compatible_health,
    next_available_port,
    port_available,
    read_health,
)
from desktop.icon import apply_macos_app_icon, resolve_icon_png


def main() -> None:
    settings = get_settings()
    runtime = settings.runtime_dir
    runtime.mkdir(parents=True, exist_ok=True)

    backend_port = settings.backend_port
    backend_url = f"http://{settings.backend_host}:{backend_port}"
    backend: subprocess.Popen[bytes] | None = None
    health = read_health(f"{backend_url}/api/health")
    if is_compatible_health(health):
        print(f"Reusing compatible backend at {backend_url}")
    else:
        if health is not None or not port_available(settings.backend_host, backend_port):
            backend_port = next_available_port(settings.backend_host, settings.backend_port + 1)
            backend_url = f"http://{settings.backend_host}:{backend_port}"
            print(f"Configured backend port is occupied by another service; using {backend_url}")
        backend = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.app.main:app",
                "--host",
                settings.backend_host,
                "--port",
                str(backend_port),
            ]
        )
        (runtime / "backend.pid").write_text(str(backend.pid))

    frontend_port = settings.frontend_port
    if not port_available(settings.frontend_host, frontend_port):
        frontend_port = next_available_port(settings.frontend_host, frontend_port + 1)
    url = f"http://{settings.frontend_host}:{frontend_port}"
    frontend_env = os.environ.copy()
    frontend_env["VITE_API_BASE"] = f"{backend_url}/api"
    frontend = subprocess.Popen(
        [
            "npm",
            "--workspace",
            "frontend",
            "run",
            "dev",
            "--",
            "--host",
            settings.frontend_host,
            "--port",
            str(frontend_port),
        ],
        env=frontend_env,
    )
    (runtime / "frontend.pid").write_text(str(frontend.pid))
    _wait_for_backend(f"{backend_url}/api/health")
    _wait_for(url)
    try:
        import webview

        apply_macos_app_icon()
        _create_window(webview, url)
        webview.start()
    except Exception:
        print(f"SDS Quantum Metric: {url}")
        try:
            while (backend is None or backend.poll() is None) and frontend.poll() is None:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    finally:
        _terminate(frontend)
        if backend is not None:
            _terminate(backend)


def _wait_for(url: str) -> None:
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310
                if response.status < 500:
                    return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url}")


def _wait_for_backend(url: str) -> None:
    deadline = time.time() + 60
    while time.time() < deadline:
        if is_compatible_health(read_health(url)):
            return
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for compatible backend {url}")


def _create_window(webview: Any, url: str) -> object:
    kwargs: dict[str, object] = {"width": 1320, "height": 900}
    icon = resolve_icon_png()
    if icon:
        kwargs["icon"] = icon
    try:
        return webview.create_window("SDS Quantum Metric", url, **kwargs)
    except TypeError as exc:
        if "icon" not in kwargs or "icon" not in str(exc):
            raise
        kwargs.pop("icon")
        return webview.create_window("SDS Quantum Metric", url, **kwargs)


def _terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


if __name__ == "__main__":
    main()
