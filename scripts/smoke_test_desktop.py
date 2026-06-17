from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config.paths import default_user_data_dir, frontend_dist_path
from backend.app.main import create_app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()

    dist = frontend_dist_path()
    _require((dist / "index.html").exists(), "frontend/dist/index.html is required.")
    _require(default_user_data_dir().name == "SDS Quantum Metric", "Unexpected data dir name.")
    _require(
        default_user_data_dir().resolve() != (Path.cwd() / "data").resolve(),
        "Default data dir must not point to ./data.",
    )

    client = TestClient(create_app())
    _require(client.get("/api/health").json() == {"status": "ok"}, "Healthcheck failed.")
    html = client.get("/").text
    _require("<!doctype html>" in html.lower(), "SPA index was not served.")
    _require("vite" not in html.lower(), "Packaged app must not depend on Vite.")
    _require(".venv" not in html.lower(), "Packaged app must not reference .venv.")

    if not args.preflight:
        artifact = _artifact_path()
        _require(artifact.exists(), f"Desktop artifact not found: {artifact}")
        _require(dist.exists(), "Built frontend dist is missing.")
        _require(
            _bundled_playwright_browsers_exist(artifact),
            "Desktop artifact must bundle Playwright Chromium.",
        )


def _artifact_path() -> Path:
    if sys.platform == "darwin":
        return Path("dist/SDS Quantum Metric.app")
    if sys.platform == "win32":
        return Path("dist/SDS Quantum Metric/SDS Quantum Metric.exe")
    return Path("dist/SDS Quantum Metric/SDS Quantum Metric")


def _bundled_playwright_browsers_exist(artifact: Path) -> bool:
    root = artifact if artifact.is_dir() else artifact.parent
    return any(path.is_dir() and any(path.iterdir()) for path in root.rglob(".local-browsers"))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


if __name__ == "__main__":
    main()
