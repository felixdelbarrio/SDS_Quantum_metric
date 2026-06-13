from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from backend.app.config.settings import get_settings


def main() -> None:
    settings = get_settings()
    runtime = settings.runtime_dir
    runtime.mkdir(parents=True, exist_ok=True)
    backend = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            settings.backend_host,
            "--port",
            str(settings.backend_port),
        ]
    )
    (runtime / "backend.pid").write_text(str(backend.pid))
    frontend = subprocess.Popen(["npm", "--workspace", "frontend", "run", "dev"])
    (runtime / "frontend.pid").write_text(str(frontend.pid))
    url = f"http://{settings.frontend_host}:{settings.frontend_port}"
    _wait_for(f"http://{settings.backend_host}:{settings.backend_port}/api/health")
    _wait_for(url)
    try:
        import webview

        _create_window(webview, url)
        webview.start()
    except Exception:
        print(f"SDS Quantum Metric: {url}")
        try:
            while backend.poll() is None and frontend.poll() is None:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    finally:
        _terminate(frontend)
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


def _create_window(webview: Any, url: str) -> object:
    kwargs: dict[str, object] = {"width": 1320, "height": 900}
    icon = Path("desktop/assets/icon.png").resolve()
    if icon.exists():
        kwargs["icon"] = str(icon)
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
