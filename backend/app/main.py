from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import router
from backend.app.config.paths import frontend_dist_path
from backend.app.config.settings import get_settings

LOGGER = logging.getLogger(__name__)


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
        allow_origin_regex=r"http://(127\.0\.0\.1|localhost):517[3-9]",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    try:
        dist = frontend_dist_path()
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str = "") -> FileResponse:
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="API route not found")
            return FileResponse(dist / "index.html")
    except FileNotFoundError:
        LOGGER.exception("Static frontend not available.")

    return app


app = create_app()
