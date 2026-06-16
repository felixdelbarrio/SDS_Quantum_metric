from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from backend.app.auth.browser_cookies import BrowserCookie
from backend.app.config.settings import Settings
from backend.app.ingestion.policy import IngestionRange, apply_ingestion_range
from backend.app.observability.sanitizer import sanitize
from backend.app.storage.parquet_store import hash_json


def capture_quantum_analytics(
    *,
    settings: Settings,
    cookies: list[BrowserCookie],
    country: str,
    base_url: str,
    dashboard_url: str,
    wait_seconds: int,
    ingestion_id: str | None = None,
    ingestion_range: IngestionRange | None = None,
) -> list[dict[str, Any]]:
    ingestion_id = ingestion_id or str(uuid.uuid4())
    ingestion_ts = datetime.now(UTC).isoformat()
    rows: list[dict[str, Any]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(settings.chrome_executable),
            headless=True,
            args=["--disable-dev-shm-usage", "--no-first-run", "--disable-background-networking"],
        )
        context = browser.new_context(ignore_https_errors=not settings.qm_verify_tls)
        context.add_cookies(cast(Any, [cookie.as_playwright() for cookie in cookies]))
        page = context.new_page()
        quantum_host = urlparse(str(base_url)).hostname

        def is_quantum_analytics(url: str) -> bool:
            parsed = urlparse(url)
            return parsed.hostname == quantum_host and parsed.path in {
                "/analytics",
                "/analytics/historical",
            }

        def on_route(route: Any) -> None:
            request = route.request
            if request.method != "POST" or not ingestion_range:
                route.continue_()
                return
            if not is_quantum_analytics(request.url):
                route.continue_()
                return
            request_json = _parse_json(request.post_data or "")
            rewritten, changed = apply_ingestion_range(request_json, ingestion_range)
            if changed:
                route.continue_(
                    post_data=json.dumps(rewritten, ensure_ascii=False, separators=(",", ":"))
                )
                return
            route.continue_()

        def on_response(response: Any) -> None:
            parsed = urlparse(response.url)
            if not is_quantum_analytics(response.url):
                return
            request = response.request
            request_json = _parse_json(request.post_data or "")
            response_json = _parse_json(response.body().decode("utf-8", "replace"))
            query = (
                request_json.get("query") if parsed.path.endswith("historical") else request_json
            )
            metadata = query.get("metadata", {}) if isinstance(query, dict) else {}
            metric_ids = metadata.get("metricIds") or []
            response_rows = response_json.get("rows") if isinstance(response_json, dict) else None
            rows.append(
                {
                    "ingestion_id": ingestion_id,
                    "ingestion_ts": ingestion_ts,
                    "country": country,
                    "source_endpoint": parsed.path,
                    "endpoint": parsed.path,
                    "http_method": request.method,
                    "method": request.method,
                    "status_code": response.status,
                    "dashboard_id": metadata.get("dashboardId"),
                    "card_id": metadata.get("cardId"),
                    "card_title": metadata.get("cardTitle") or metadata.get("title"),
                    "card_role": metadata.get("cardRole") or metadata.get("visualRole"),
                    "card_type": metadata.get("cardType"),
                    "view_name": metadata.get("viewName"),
                    "request_headers_sanitized": json.dumps(
                        _sanitize_headers(request.headers),
                        ensure_ascii=False,
                    ),
                    "metric_ids": json.dumps(metric_ids, ensure_ascii=False),
                    "query_hash": hash_json(request_json),
                    "response_hash": hash_json(response_json),
                    "request_json": json.dumps(sanitize(request_json), ensure_ascii=False),
                    "response_json": json.dumps(sanitize(response_json), ensure_ascii=False),
                    "row_count": len(response_rows) if isinstance(response_rows, list) else 0,
                    "parse_status": "pending",
                    "parse_error": None,
                    "captured_at": ingestion_ts,
                    "source_ts_start": (request_json.get("ts") or [None, None])[0]
                    if isinstance(request_json.get("ts"), list)
                    else None,
                    "source_ts_end": (request_json.get("ts") or [None, None])[1]
                    if isinstance(request_json.get("ts"), list)
                    else None,
                }
            )

        page.route("**/*", on_route)
        page.on("response", on_response)
        page.goto(dashboard_url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(wait_seconds * 1000)
        browser.close()
    return rows


def _parse_json(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {"value": value}


def _sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    blocked = {"cookie", "authorization", "x-csrf", "x-csrf-token", "x-xsrf-token"}
    return {
        key: value
        for key, value in sanitize(headers).items()
        if key.casefold() not in blocked and "token" not in key.casefold()
    }
