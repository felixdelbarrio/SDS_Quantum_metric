from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import router
from backend.app.config.settings import get_settings


def _frontend_dist_path() -> Path:
    candidates = []
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "frontend" / "dist")  # type: ignore[attr-defined]
    candidates.extend(
        [
            Path.cwd() / "frontend" / "dist",
            Path(__file__).resolve().parents[3] / "frontend" / "dist",
        ]
    )
    return next((path for path in candidates if path.exists()), candidates[-1])


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="SDS Quantum Metric", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            f"http://{settings.frontend_host}:{settings.frontend_port}",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    dist = _frontend_dist_path()
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str = "") -> FileResponse:
            _ = full_path
            return FileResponse(dist / "index.html")

    return app


app = create_app()
