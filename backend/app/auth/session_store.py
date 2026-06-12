from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


@dataclass
class ManualSecret:
    cookie_header: str | None = None


class SessionSecretStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._manual = ManualSecret()

    def set_manual_cookie(self, cookie_header: str | None) -> None:
        with self._lock:
            self._manual.cookie_header = cookie_header or None

    def get_manual_cookie(self) -> str | None:
        with self._lock:
            return self._manual.cookie_header

    def clear(self) -> None:
        with self._lock:
            self._manual = ManualSecret()


secret_store = SessionSecretStore()
