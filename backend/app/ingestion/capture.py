from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from backend.app.auth.browser_cookies import BrowserCookie
from backend.app.config.settings import Settings
from backend.app.ingestion.planner import IngestionChunk
from backend.app.ingestion.policy import IngestionRange, apply_ingestion_range
from backend.app.ingestion.time_rewriter import (
    extract_query_time_range,
    validate_query_time_range,
)
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
    session_mode: str = "manual",
) -> list[dict[str, Any]]:
    with QuantumAnalyticsCaptureSession(
        settings=settings,
        cookies=cookies,
        country=country,
        base_url=base_url,
        wait_seconds=wait_seconds,
        ingestion_id=ingestion_id,
        session_mode=session_mode,
    ) as session:
        return session.capture(dashboard_url=dashboard_url, ingestion_range=ingestion_range)


class QuantumAnalyticsCaptureSession:
    def __init__(
        self,
        *,
        settings: Settings,
        cookies: list[BrowserCookie],
        country: str,
        base_url: str,
        wait_seconds: int,
        ingestion_id: str | None = None,
        session_mode: str = "manual",
    ) -> None:
        self.settings = settings
        self.cookies = cookies
        self.country = country
        self.base_url = base_url
        self.wait_seconds = wait_seconds
        self.ingestion_id = ingestion_id or str(uuid.uuid4())
        self.session_mode = session_mode
        self.quantum_host = urlparse(str(base_url)).hostname
        self._playwright_manager: Any | None = None
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._context: Any | None = None

    def __enter__(self) -> QuantumAnalyticsCaptureSession:
        _configure_playwright_browser_path()
        self._playwright_manager = sync_playwright()
        try:
            self._playwright = self._playwright_manager.start()
        except AttributeError as exc:
            if "_playwright" in str(exc):
                raise RuntimeError(
                    "Playwright could not start its browser driver for ingestion capture. "
                    "Run `make setup` to reinstall browser assets and retry ingestion."
                ) from exc
            raise
        if self.session_mode == "controlled":
            user_data_dir = self.settings.runtime_dir / "quantum-controlled-profile"
            user_data_dir.mkdir(parents=True, exist_ok=True)
            self._context = self._playwright.chromium.launch_persistent_context(
                str(user_data_dir),
                headless=True,
                ignore_https_errors=not self.settings.qm_verify_tls,
                args=["--disable-dev-shm-usage", "--no-first-run"],
            )
            if self.cookies:
                self._context.add_cookies(
                    cast(Any, [cookie.as_playwright() for cookie in self.cookies])
                )
        else:
            self._browser = _launch_headless_browser(self._playwright, self.settings)
            self._context = self._browser.new_context(
                ignore_https_errors=not self.settings.qm_verify_tls
            )
            self._context.add_cookies(
                cast(Any, [cookie.as_playwright() for cookie in self.cookies])
            )
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._context is not None:
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    def capture(
        self,
        *,
        dashboard_url: str,
        ingestion_range: IngestionRange | None,
    ) -> list[dict[str, Any]]:
        if self._context is None:
            raise RuntimeError("Capture session is not started.")
        ingestion_ts = datetime.now(UTC).isoformat()
        rows: list[dict[str, Any]] = []
        range_validation_errors: list[str] = []
        console_errors: list[str] = []
        request_failures: list[str] = []
        analytics_state: dict[str, Any] = {
            "requests": 0,
            "responses": 0,
            "last_response_at": time.monotonic(),
            "statuses": [],
            "range_validation_errors": 0,
        }
        routed_payloads_by_id: dict[int, dict[str, Any]] = {}
        routed_payloads_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
        page = self._context.new_page()

        def on_route(route: Any) -> None:
            request = route.request
            if request.method != "POST" or not ingestion_range:
                route.continue_()
                return
            if not self._is_quantum_analytics(request.url):
                route.continue_()
                return
            analytics_state["requests"] = int(analytics_state["requests"]) + 1
            raw_post_data = request.post_data or ""
            request_json = _parse_json(raw_post_data)
            rewritten, changed = apply_ingestion_range(request_json, ingestion_range)
            routed_payloads_by_id[id(request)] = rewritten if changed else request_json
            routed_payloads_by_key[(request.method, request.url, raw_post_data)] = (
                rewritten if changed else request_json
            )
            if changed:
                route.continue_(
                    post_data=json.dumps(rewritten, ensure_ascii=False, separators=(",", ":"))
                )
                return
            route.continue_()

        def on_response(response: Any) -> None:
            parsed = urlparse(response.url)
            if not self._is_quantum_analytics(response.url):
                return
            analytics_state["responses"] = int(analytics_state["responses"]) + 1
            analytics_state["last_response_at"] = time.monotonic()
            cast(list[int], analytics_state["statuses"]).append(int(response.status))
            request = response.request
            raw_post_data = request.post_data or ""
            request_json = routed_payloads_by_id.pop(id(request), None)
            if request_json is None:
                request_json = routed_payloads_by_key.pop(
                    (request.method, request.url, raw_post_data),
                    _parse_json(raw_post_data),
                )
            try:
                response_json = _parse_json(response.body().decode("utf-8", "replace"))
            except Exception:
                response_json = {}
            query_range = extract_query_time_range(request_json)
            range_validation = None
            if ingestion_range is not None:
                validation_target = IngestionChunk(
                    start=ingestion_range.start,
                    end=ingestion_range.end,
                    label=f"{_iso(ingestion_range.start)} -> {_iso(ingestion_range.end)}",
                )
                range_validation = validate_query_time_range(request_json, validation_target)
                if range_validation.status != "passed":
                    message = range_validation.error or "Range validation failed."
                    analytics_state["range_validation_errors"] = (
                        int(analytics_state["range_validation_errors"]) + 1
                    )
                    range_validation_errors.append(f"{parsed.path}: {message}")
                    return
            query = (
                request_json.get("query") if parsed.path.endswith("historical") else request_json
            )
            metadata = query.get("metadata", {}) if isinstance(query, dict) else {}
            metric_ids = metadata.get("metricIds") or []
            response_rows = response_json.get("rows") if isinstance(response_json, dict) else None
            rows.append(
                {
                    "ingestion_id": self.ingestion_id,
                    "ingestion_ts": ingestion_ts,
                    "country": self.country,
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
                    "source_ts_start": _iso(query_range.start) if query_range else None,
                    "source_ts_end": _iso(query_range.end) if query_range else None,
                    "source_period_label": query_range.label if query_range else None,
                    "source_timezone": query_range.timezone if query_range else "CST",
                    "capture_chunk_start": _iso(ingestion_range.start) if ingestion_range else None,
                    "capture_chunk_end": _iso(ingestion_range.end) if ingestion_range else None,
                    "range_key": ingestion_range.range_key if ingestion_range else "custom",
                    "range_start": _iso(ingestion_range.start) if ingestion_range else None,
                    "range_end": _iso(ingestion_range.end) if ingestion_range else None,
                    "range_timezone": ingestion_range.timezone if ingestion_range else "CST",
                    "capture_mode": ingestion_range.capture_mode
                    if ingestion_range
                    else "range_contract",
                    "requested_range_start": _iso(range_validation.requested_start)
                    if range_validation
                    else None,
                    "requested_range_end": _iso(range_validation.requested_end)
                    if range_validation
                    else None,
                    "extracted_range_start": _iso(range_validation.extracted_start)
                    if range_validation and range_validation.extracted_start
                    else None,
                    "extracted_range_end": _iso(range_validation.extracted_end)
                    if range_validation and range_validation.extracted_end
                    else None,
                    "range_validation_status": range_validation.status
                    if range_validation
                    else "not_applicable",
                    "range_validation_error": range_validation.error if range_validation else None,
                    "time_rewrite_status": "rewritten" if ingestion_range else "original",
                }
            )

        def on_console(message: Any) -> None:
            if message.type in {"error", "warning"}:
                console_errors.append(f"{message.type}: {message.text}"[:240])

        def on_request_failed(request: Any) -> None:
            if self._is_quantum_analytics(request.url):
                failure = request.failure
                request_failures.append(str(failure or request.url)[:240])

        _prepare_dashboard_page(page)
        page.route("**/*", on_route)
        page.on("response", on_response)
        page.on("console", on_console)
        page.on("requestfailed", on_request_failed)
        try:
            page.goto(dashboard_url, wait_until="domcontentloaded", timeout=60_000)
            _wait_for_analytics_settle(page, rows, analytics_state, self.wait_seconds)
        finally:
            diagnostics = _capture_diagnostics(
                page,
                analytics_state,
                console_errors=console_errors,
                request_failures=request_failures,
            )
            page.close()
        if range_validation_errors and not rows:
            unique_errors = list(dict.fromkeys(range_validation_errors))
            raise RuntimeError(
                "Quantum range validation failed before persisting raw calls: "
                + " | ".join(unique_errors[:5])
            )
        if not rows:
            raise RuntimeError("No Quantum analytics responses were captured. " + diagnostics)
        return rows

    def _is_quantum_analytics(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.hostname == self.quantum_host and parsed.path in {
            "/analytics",
            "/analytics/historical",
        }


def _launch_headless_browser(playwright: Any, settings: Settings) -> Any:
    args = ["--disable-dev-shm-usage", "--no-first-run", "--disable-background-networking"]
    try:
        return playwright.chromium.launch(headless=True, args=args)
    except Exception as exc:
        raise RuntimeError(
            "Playwright Chromium is not available for ingestion capture. "
            "Run `make setup` and rebuild the desktop artifact with `make build`."
        ) from exc


def _configure_playwright_browser_path() -> None:
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return
    if _running_frozen() or _packaged_playwright_browsers_exist():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"


def _running_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _packaged_playwright_browsers_exist() -> bool:
    try:
        import playwright
    except ImportError:
        return False
    package_root = Path(playwright.__file__).resolve().parent
    candidates = [
        package_root / "driver/package/.local-browsers",
        Path(getattr(sys, "_MEIPASS", "")) / "playwright/driver/package/.local-browsers",
    ]
    return any(path.exists() and any(path.iterdir()) for path in candidates)


def _parse_json(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {"value": value}


def _wait_for_analytics_settle(
    page: Any,
    rows: list[dict[str, Any]],
    analytics_state: dict[str, Any],
    wait_seconds: int,
) -> None:
    started = time.monotonic()
    deadline = started + max(5, wait_seconds)
    quiet_seconds = 8.0
    minimum_seconds = 35.0
    next_scroll_at = started + 2.0
    while time.monotonic() < deadline:
        page.wait_for_timeout(500)
        now = time.monotonic()
        if now >= next_scroll_at:
            _scroll_dashboard(page)
            next_scroll_at = now + 1.5
        if rows and now - started >= minimum_seconds:
            last_response_at = float(analytics_state.get("last_response_at") or started)
            if now - last_response_at >= quiet_seconds:
                return
        if not rows and now - started >= 8 and _looks_unauthenticated(page):
            return


def _prepare_dashboard_page(page: Any) -> None:
    try:
        page.set_viewport_size({"width": 1920, "height": 2400})
    except Exception:
        return


def _scroll_dashboard(page: Any) -> None:
    try:
        page.evaluate(
            """
            () => {
              const doc = document.documentElement;
              const body = document.body;
              const maxY = Math.max(body.scrollHeight, doc.scrollHeight) - window.innerHeight;
              if (maxY <= 0) return;
              const step = Math.max(Math.floor(window.innerHeight * 0.75), 600);
              const next = window.scrollY + step >= maxY ? 0 : window.scrollY + step;
              window.scrollTo({ top: next, behavior: "auto" });
            }
            """
        )
    except Exception:
        return


def _capture_diagnostics(
    page: Any,
    analytics_state: dict[str, Any],
    *,
    console_errors: list[str],
    request_failures: list[str],
) -> str:
    try:
        title = page.title()
    except Exception:
        title = ""
    try:
        final_url = page.url
    except Exception:
        final_url = ""
    auth_hint = " login_detected=true" if _looks_unauthenticated(page) else ""
    statuses = ",".join(str(status) for status in analytics_state.get("statuses", [])[-10:])
    return (
        f"final_url={final_url or '-'} title={title or '-'}"
        f" analytics_requests={analytics_state.get('requests', 0)}"
        f" analytics_responses={analytics_state.get('responses', 0)}"
        f" analytics_statuses={statuses or '-'}"
        f" range_validation_errors={analytics_state.get('range_validation_errors', 0)}"
        f"{auth_hint}"
        f" request_failures={request_failures[:3]}"
        f" console={console_errors[:3]}"
    )


def _looks_unauthenticated(page: Any) -> bool:
    try:
        current = f"{page.url} {page.title()}".casefold()
    except Exception:
        current = ""
    auth_markers = (
        "login",
        "signin",
        "sign-in",
        "saml",
        "oauth",
        "authenticate",
        "microsoftonline",
        "okta",
    )
    return any(marker in current for marker in auth_markers)


def _sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    blocked = {"cookie", "authorization", "x-csrf", "x-csrf-token", "x-xsrf-token"}
    return {
        key: value
        for key, value in sanitize(headers).items()
        if key.casefold() not in blocked and "token" not in key.casefold()
    }


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
