from __future__ import annotations

import socket

from backend.app.runtime import API_SCHEMA_VERSION, APP_ID
from desktop.backend_runtime import is_compatible_health, next_available_port


def test_desktop_reuses_only_schema_compatible_backends() -> None:
    assert is_compatible_health({"status": "ok", "app": APP_ID, "api_schema": API_SCHEMA_VERSION})
    assert not is_compatible_health({"status": "ok"})
    assert not is_compatible_health({"status": "ok", "app": APP_ID, "api_schema": "old"})


def test_desktop_finds_next_available_port() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        occupied = busy.getsockname()[1]

        assert next_available_port("127.0.0.1", occupied) != occupied
