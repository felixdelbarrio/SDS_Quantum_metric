from __future__ import annotations

import hashlib
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from backend.app.config.settings import Settings


@dataclass(frozen=True)
class BrowserCookie:
    name: str
    value: str
    domain: str
    path: str = "/"
    secure: bool = True
    http_only: bool = False
    expires: float | None = None

    def matches(self, hostname: str) -> bool:
        domain = self.domain.lstrip(".")
        return hostname == domain or hostname.endswith(f".{domain}")

    def as_pair(self) -> str:
        return f"{self.name}={self.value}"

    def as_playwright(self) -> dict[str, object]:
        cookie: dict[str, object] = {
            "name": self.name,
            "value": self.value,
            "domain": self.domain,
            "path": self.path,
            "secure": self.secure,
            "httpOnly": self.http_only,
        }
        if self.expires:
            cookie["expires"] = self.expires
        return cookie


class CookieAccessError(RuntimeError):
    pass


class BrowserCookieProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def load(self, browser: str, base_url: str) -> list[BrowserCookie]:
        normalized = browser.lower()
        if normalized != "chrome":
            raise CookieAccessError(
                f"Browser '{browser}' is not implemented yet. Use Chrome or Manual mode."
            )
        return self._load_chrome(base_url)

    def from_manual_header(self, cookie_header: str, base_url: str) -> list[BrowserCookie]:
        hostname = urlparse(base_url).hostname or "localhost"
        cookies: list[BrowserCookie] = []
        for part in cookie_header.split(";"):
            if "=" not in part:
                continue
            name, value = part.strip().split("=", 1)
            if name and value:
                cookies.append(BrowserCookie(name=name, value=value, domain=hostname))
        if not cookies:
            raise CookieAccessError("Manual cookie is empty or invalid.")
        return cookies

    def cookie_header(self, cookies: list[BrowserCookie], url: str) -> str:
        hostname = urlparse(url).hostname or ""
        return "; ".join(cookie.as_pair() for cookie in cookies if cookie.matches(hostname))

    def _load_chrome(self, base_url: str) -> list[BrowserCookie]:
        hostname = urlparse(base_url).hostname
        if not hostname:
            raise CookieAccessError("Invalid Quantum base URL.")
        db_path = self._chrome_cookie_db()
        if not db_path.exists():
            raise CookieAccessError(
                f"Chrome cookie DB not found for profile {self.settings.chrome_cookie_profile}."
            )
        key = self._chrome_safe_storage_key()
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                """
                SELECT host_key, name, path, is_secure, is_httponly, expires_utc, encrypted_value
                FROM cookies
                WHERE host_key LIKE ?
                   OR host_key LIKE ?
                   OR host_key LIKE ?
                """,
                ("%quantummetric.com%", f"%{hostname}", "%.iam.quantummetric.com%"),
            ).fetchall()
        finally:
            con.close()
        cookies: list[BrowserCookie] = []
        for row in rows:
            encrypted = row["encrypted_value"]
            if not encrypted or not encrypted.startswith(b"v10"):
                continue
            value = self._decrypt_chrome_value(row["host_key"], encrypted, key)
            if not value:
                continue
            cookies.append(
                BrowserCookie(
                    name=row["name"],
                    value=value,
                    domain=row["host_key"],
                    path=row["path"] or "/",
                    secure=bool(row["is_secure"]),
                    http_only=bool(row["is_httponly"]),
                    expires=self._chrome_expires_to_unix(row["expires_utc"]),
                )
            )
        if not cookies:
            raise CookieAccessError("No Quantum Metric cookies were available in Chrome.")
        return cookies

    def _chrome_cookie_db(self) -> Path:
        return (
            Path.home()
            / "Library/Application Support/Google/Chrome"
            / self.settings.chrome_cookie_profile
            / "Cookies"
        )

    def _chrome_safe_storage_key(self) -> bytes:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-w",
                "-s",
                "Chrome Safe Storage",
                "-a",
                "Chrome",
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise CookieAccessError("Chrome Safe Storage key is unavailable.")
        return hashlib.pbkdf2_hmac(
            "sha1", result.stdout.rstrip("\n").encode(), b"saltysalt", 1003, 16
        )

    def _decrypt_chrome_value(self, host_key: str, encrypted_value: bytes, key: bytes) -> str:
        proc = subprocess.run(
            [
                "openssl",
                "enc",
                "-d",
                "-aes-128-cbc",
                "-K",
                key.hex(),
                "-iv",
                (b" " * 16).hex(),
            ],
            input=encrypted_value[3:],
            capture_output=True,
            timeout=10,
            check=False,
        )
        if proc.returncode != 0:
            raise CookieAccessError("Could not decrypt a Chrome cookie.")
        plain = proc.stdout
        digest = hashlib.sha256(host_key.encode()).digest()
        if plain.startswith(digest):
            plain = plain[32:]
        return plain.decode("utf-8")

    def _chrome_expires_to_unix(self, expires_utc: int) -> float | None:
        if not expires_utc:
            return None
        unix = int(expires_utc) / 1_000_000 - 11_644_473_600
        return unix if unix > time.time() else None
