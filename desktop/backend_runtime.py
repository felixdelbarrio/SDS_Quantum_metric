from __future__ import annotations

import json
import socket
import urllib.request

from backend.app.runtime import API_SCHEMA_VERSION, APP_ID


def read_health(url: str) -> dict[str, object] | None:
    try:
        with urllib.request.urlopen(url, timeout=1) as response:  # noqa: S310
            if int(response.status) != 200:
                return None
            payload = response.read().decode("utf-8", "replace")
            data = json.loads(payload)
            return data if isinstance(data, dict) else None
    except Exception:
        return None


def is_compatible_health(health: dict[str, object] | None) -> bool:
    return bool(
        health
        and health.get("status") == "ok"
        and health.get("app") == APP_ID
        and health.get("api_schema") == API_SCHEMA_VERSION
    )


def port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def next_available_port(host: str, first_port: int) -> int:
    for port in range(first_port, first_port + 100):
        if port_available(host, port):
            return port
    raise RuntimeError("No hay puertos locales disponibles para iniciar el backend.")
