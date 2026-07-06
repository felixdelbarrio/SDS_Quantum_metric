from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

SECRET_KEY_RE = re.compile(
    r"(cookie|token|authorization|secret|password|refresh|access)", re.IGNORECASE
)
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}")
COOKIE_PAIR_RE = re.compile(r"([A-Za-z0-9_:\-.]+)=([^;\"',}\]\s]{12,})")


def redact_text(value: str) -> str:
    value = JWT_RE.sub("<redacted-jwt>", value)
    return COOKIE_PAIR_RE.sub(lambda m: f"{m.group(1)}=<redacted>", value)


def sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize(item) for item in value)
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            sanitized[key_text] = "<redacted>" if SECRET_KEY_RE.search(key_text) else sanitize(item)
        return sanitized
    return value


def sanitize_error(exc: BaseException) -> str:
    return "An internal error occurred while processing the request."
