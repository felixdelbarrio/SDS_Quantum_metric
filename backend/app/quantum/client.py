from __future__ import annotations

import json
import ssl
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

import httpx
import truststore

from backend.app.auth.browser_cookies import BrowserCookie, BrowserCookieProvider
from backend.app.config.settings import Settings
from backend.app.observability.sanitizer import sanitize, sanitize_error
from backend.app.quantum.schemas import QuantumConfig, TestConnectionResponse


class QuantumClient:
    def __init__(
        self,
        settings: Settings,
        config: QuantumConfig,
        cookie_provider: BrowserCookieProvider,
        cookies: list[BrowserCookie],
    ) -> None:
        self.settings = settings
        self.config = config
        self.cookie_provider = cookie_provider
        self.cookies = cookies

    def test_connection(self) -> TestConnectionResponse:
        started = time.perf_counter()
        endpoint = str(urljoin(str(self.config.base_url), "/data/init"))
        try:
            with self._client() as client:
                init_response = client.get(
                    endpoint,
                    headers=self._cookie_headers(endpoint),
                )
                init_response.raise_for_status()
                init_json = init_response.json()
                auth_endpoint = str(urljoin(str(self.config.base_url), "/auth-token"))
                token_response = client.get(
                    auth_endpoint, headers=self._cookie_headers(auth_endpoint)
                )
                token_response.raise_for_status()
                token_json = token_response.json()
                access_token = token_json.get("accessToken") or token_json.get(
                    "qmVisible.accessToken"
                )
                if not access_token:
                    raise RuntimeError(
                        "Quantum auth-token response did not include an access token."
                    )
                qm_services = init_json.get("qmServicesEndpoint") or "https://api.quantummetric.com"
                query_endpoint = str(urljoin(qm_services, "/query"))
                gql_response = client.post(
                    query_endpoint,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {access_token}",
                    },
                    content=json.dumps(
                        {"query": "query { permissions { id handle accessLevel } }"}
                    ),
                )
                gql_response.raise_for_status()
                gql_json = gql_response.json()
                permissions = gql_json.get("data", {}).get("permissions", [])
            latency = (time.perf_counter() - started) * 1000
            return TestConnectionResponse(
                status="ok",
                endpoint_tested=query_endpoint,
                latency_ms=round(latency, 2),
                timestamp=datetime.now(UTC),
                message="Conexion autenticada correcta.",
                details={
                    "base_url_status": init_response.status_code,
                    "query_status": gql_response.status_code,
                    "permissions_count": len(permissions)
                    if isinstance(permissions, list)
                    else None,
                    "qm_services_endpoint": qm_services,
                    "is_user_authenticated": bool(init_json.get("isUserAuthenticated")),
                },
            )
        except Exception as exc:
            latency = (time.perf_counter() - started) * 1000
            return TestConnectionResponse(
                status="ko",
                endpoint_tested=endpoint,
                latency_ms=round(latency, 2),
                timestamp=datetime.now(UTC),
                message="No se pudo validar la conexion Quantum.",
                error=sanitize_error(exc),
            )

    def _client(self) -> httpx.Client:
        verify: bool | ssl.SSLContext
        if self.config.verify_tls:
            verify = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        else:
            verify = False
        return httpx.Client(timeout=30, verify=verify, follow_redirects=True)

    def _cookie_headers(self, endpoint: str) -> dict[str, str]:
        return {
            "Cookie": self.cookie_provider.cookie_header(self.cookies, endpoint),
            "User-Agent": "Mozilla/5.0 QuantumMetricLocal/0.1",
        }


def sanitized_json(value: Any) -> str:
    return json.dumps(sanitize(value), ensure_ascii=False, separators=(",", ":"))
