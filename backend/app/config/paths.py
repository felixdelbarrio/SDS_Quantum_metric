from __future__ import annotations

import sys
from pathlib import Path

from platformdirs import user_data_dir, user_log_dir

APP_NAME = "SDS Quantum Metric"
APP_AUTHOR = "SDS"


def is_packaged() -> bool:
    return bool(getattr(sys, "frozen", False)) or hasattr(sys, "_MEIPASS")


def app_bundle_root() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[3]


def default_user_data_dir() -> Path:
    return Path(user_data_dir(APP_NAME, APP_AUTHOR))


def default_user_log_dir() -> Path:
    return Path(user_log_dir(APP_NAME, APP_AUTHOR))


def frontend_dist_path() -> Path:
    candidates = [
        app_bundle_root() / "frontend" / "dist",
        Path.cwd() / "frontend" / "dist",
        Path(__file__).resolve().parents[3] / "frontend" / "dist",
    ]
    for candidate in candidates:
        if (candidate / "index.html").exists():
            return candidate
    raise FileNotFoundError(
        "frontend/dist/index.html not found. Run npm run build before packaging."
    )
