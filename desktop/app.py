from __future__ import annotations

import threading
import time
import urllib.request

import uvicorn

from backend.app.config.settings import get_settings
from backend.app.main import app


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

        webview.create_window("SDS Quantum Metric", url, width=1320, height=900)
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


if __name__ == "__main__":
    main()
