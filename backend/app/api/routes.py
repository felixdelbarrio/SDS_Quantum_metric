from __future__ import annotations

import os
import shutil
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.app.analytics.models import SortDirection
from backend.app.analytics.service import AnalyticsService
from backend.app.auth.browser_cookies import BrowserCookie, BrowserCookieProvider
from backend.app.auth.session_store import secret_store
from backend.app.config.settings import Settings, get_settings
from backend.app.ingestion.models import (
    IngestionCreate,
    MissingDaysIngestionCreate,
    RangeIngestionCreate,
)
from backend.app.ingestion.service import IngestionService
from backend.app.quantum.client import QuantumClient
from backend.app.quantum.config_store import QuantumConfigStore
from backend.app.quantum.schemas import (
    QuantumConfig,
    QuantumConfigUpdate,
    QuantumCountryConfig,
    QuantumDashboardConfig,
    QuantumPublicConfig,
    QuantumPublicConfigUpdate,
    QuantumWidgetConfig,
    merge_public_quantum_update,
    public_quantum_config,
)
from backend.app.quantum_dashboard.builder import build_derived_datasets
from backend.app.quantum_dashboard.dashboard_discovery import (
    QuantumDashboardSummary,
    dashboards_from_config_cache,
    discover_dashboards_via_browser,
)
from backend.app.quantum_dashboard.dashboard_resources import (
    DashboardResourceSource,
    DashboardResourcesResult,
    QuantumDashboardResource,
    read_dashboard_resources_cache,
    resources_from_dashboard_configs,
    result_from_resource_rows,
    write_dashboard_resources_cache,
)
from backend.app.quantum_dashboard.dashboard_structure import (
    discover_dashboard_structure_via_browser,
    structure_from_dashboard_config,
    tab_configs_from_structure,
    widget_configs_from_structure,
)
from backend.app.quantum_dashboard.discovery import discover_dashboard_from_config
from backend.app.quantum_dashboard.evidence import build_evidence_report
from backend.app.quantum_dashboard.manual_dashboard import (
    ManualDashboardRequest,
    manual_dashboard_input_from_request,
)
from backend.app.quantum_dashboard.range_query import range_resolution_payload, resolve_range
from backend.app.quantum_dashboard.regression import run_regression
from backend.app.quantum_dashboard.service import LocalDashboardService
from backend.app.runtime import API_SCHEMA_VERSION, APP_ID, APP_NAME
from backend.app.storage.parquet_store import ParquetStore

router = APIRouter(prefix="/api")
_INGESTION_SERVICE: IngestionService | None = None
DashboardConfigSource = Literal["quantum_api", "quantum_web", "config_cache", "manual"]


class DatasetExportRequest(BaseModel):
    countries: list[str] = Field(default_factory=list)
    export_path: str | None = None


def settings_dep() -> Settings:
    return get_settings()


def config_store_dep(settings: Annotated[Settings, Depends(settings_dep)]) -> QuantumConfigStore:
    return QuantumConfigStore(settings)


def parquet_store_dep(settings: Annotated[Settings, Depends(settings_dep)]) -> ParquetStore:
    return ParquetStore(settings)


def cookie_provider_dep(
    settings: Annotated[Settings, Depends(settings_dep)],
) -> BrowserCookieProvider:
    return BrowserCookieProvider(settings)


def ingestion_service_dep(
    settings: Annotated[Settings, Depends(settings_dep)],
    config_store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    parquet_store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    cookie_provider: Annotated[BrowserCookieProvider, Depends(cookie_provider_dep)],
) -> IngestionService:
    global _INGESTION_SERVICE
    if _INGESTION_SERVICE is None:
        _INGESTION_SERVICE = IngestionService(
            settings, config_store, parquet_store, cookie_provider
        )
    return _INGESTION_SERVICE


def _dashboard_from_summary(
    summary: QuantumDashboardSummary,
    *,
    is_default: bool,
) -> QuantumDashboardConfig:
    return QuantumDashboardConfig(
        dashboard_id=summary.dashboard_id,
        name=summary.name,
        dashboard_type=summary.type,
        team_id=summary.team_id or "",
        is_default=is_default,
        is_manual=False,
        validated=True,
        validation_status="ok",
        source=summary.source,
        discovered_at=summary.discovered_at,
    )


def _dashboard_from_resource(
    resource: QuantumDashboardResource,
    *,
    is_default: bool,
) -> QuantumDashboardConfig:
    if resource.source == "quantum_graphql":
        source: DashboardConfigSource = "quantum_api"
    elif resource.source == "manual":
        source = "manual"
    else:
        source = "config_cache"
    return QuantumDashboardConfig(
        dashboard_id=resource.dashboard_id,
        name=resource.name,
        dashboard_type=resource.type,
        team_id=resource.team_id or "",
        is_default=is_default,
        is_manual=resource.source == "manual",
        validated=True,
        validation_status="ok",
        source=source,
        discovered_at=resource.discovered_at,
    )


def _resource_from_summary(
    summary: QuantumDashboardSummary,
    *,
    source: str | None = None,
) -> QuantumDashboardResource:
    resource_source: DashboardResourceSource = (
        "cache" if summary.source == "config_cache" else "quantum_graphql"
    )
    if source in {"quantum_graphql", "manual", "cache"}:
        resource_source = cast(DashboardResourceSource, source)
    return QuantumDashboardResource(
        dashboard_id=summary.dashboard_id,
        name=summary.name if summary.name != summary.dashboard_id else "",
        type="DASHBOARD",
        starred=summary.is_default_candidate,
        country=summary.country,
        team_id=summary.team_id,
        source=resource_source,
        order=summary.order or 0,
        discovered_at=summary.discovered_at,
    )


def _upsert_dashboard(
    dashboards: list[QuantumDashboardConfig],
    dashboard: QuantumDashboardConfig,
) -> list[QuantumDashboardConfig]:
    next_dashboards: list[QuantumDashboardConfig] = []
    replaced = False
    for existing in dashboards:
        if existing.dashboard_id == dashboard.dashboard_id:
            widgets_by_role = {widget.role: widget for widget in existing.widgets}
            widgets_by_id = {
                widget.widget_id or widget.card_id or widget.role: widget
                for widget in existing.widgets
            }
            merged_widgets = [
                widget.model_copy(
                    update={
                        "enabled": _existing_widget_enabled(widget, widgets_by_role, widgets_by_id),
                        "widget_id": _existing_widget_id(widget, widgets_by_role)
                        or widget.widget_id,
                    }
                )
                for widget in dashboard.widgets
            ]
            next_dashboards.append(
                dashboard.model_copy(
                    update={
                        "widgets": merged_widgets,
                        "tabs": dashboard.tabs or existing.tabs,
                        "last_structure_at": dashboard.last_structure_at
                        or existing.last_structure_at,
                        "is_default": dashboard.is_default or existing.is_default,
                        "is_manual": dashboard.is_manual or existing.is_manual,
                    }
                )
            )
            replaced = True
            continue
        if dashboard.is_default:
            next_dashboards.append(existing.model_copy(update={"is_default": False}))
        else:
            next_dashboards.append(existing)
    if not replaced:
        next_dashboards.append(dashboard)
    return next_dashboards


def _existing_widget_enabled(
    widget: QuantumWidgetConfig,
    by_role: dict[str, QuantumWidgetConfig],
    by_id: dict[str, QuantumWidgetConfig],
) -> bool:
    existing = by_role.get(widget.role) if widget.role else None
    existing = existing or by_id.get(widget.widget_id or widget.card_id or widget.role)
    return existing.enabled if existing is not None else widget.enabled


def _existing_widget_id(
    widget: QuantumWidgetConfig,
    by_role: dict[str, QuantumWidgetConfig],
) -> str:
    existing = by_role.get(widget.role) if widget.role else None
    return existing.widget_id if existing is not None else ""


def _write_config(
    store: QuantumConfigStore,
    config: QuantumConfig,
    countries: list[QuantumCountryConfig],
) -> None:
    store.write(
        QuantumConfigUpdate(
            schema_version=config.schema_version,
            browser=config.browser,
            session_mode=config.session_mode,
            country=config.country,
            countries=countries,
            verify_tls=config.verify_tls,
            ingestion_depth_days=config.ingestion_depth_days,
            theme_preference=config.theme_preference,
            export_path=config.export_path,
        )
    )


def _validate_default_dashboards(config: QuantumConfigUpdate) -> None:
    missing = [
        country.country.value
        for country in config.countries
        if country.enabled
        and not (
            (dashboard := country.default_dashboard())
            and dashboard.dashboard_id
            and dashboard.validated
        )
    ]
    if missing:
        label = ", ".join(missing)
        raise HTTPException(
            status_code=400,
            detail=f"Selecciona un dashboard default validado para guardar: {label}.",
        )


def _cookies_for_quantum(
    config: QuantumConfig,
    country_config: QuantumCountryConfig,
    cookie_provider: BrowserCookieProvider,
) -> list[BrowserCookie]:
    if config.session_mode == "manual":
        manual_cookie = secret_store.get_manual_cookie()
        if not manual_cookie:
            raise HTTPException(
                status_code=400,
                detail="Manual session mode needs a cookie in memory.",
            )
        return cookie_provider.from_manual_header(manual_cookie, str(country_config.base_url))
    if config.session_mode == "controlled":
        return []
    return cookie_provider.load(config.browser.value, str(country_config.base_url))


def _merge_discovered_dashboards(
    country_config: QuantumCountryConfig,
    summaries: list[QuantumDashboardSummary],
) -> list[QuantumDashboardConfig]:
    existing_by_id = {dashboard.dashboard_id: dashboard for dashboard in country_config.dashboards}
    default_dashboard = country_config.default_dashboard()
    default_id = default_dashboard.dashboard_id if default_dashboard else None
    dashboards = list(country_config.dashboards)
    for summary in summaries:
        existing = existing_by_id.get(summary.dashboard_id)
        fallback_team_id = (existing.team_id if existing else "") or country_config.team_id
        is_default = summary.dashboard_id == default_id or (
            default_id is None and summary.is_default_candidate
        )
        dashboards = _upsert_dashboard(
            dashboards,
            _dashboard_from_summary(
                summary.model_copy(update={"team_id": summary.team_id or fallback_team_id}),
                is_default=is_default,
            ).model_copy(
                update={
                    "widgets": existing.widgets if existing else [],
                    "tabs": existing.tabs if existing else [],
                    "validated": True,
                    "validation_status": "ok",
                }
            ),
        )
    return dashboards


def _merge_dashboard_resources(
    country_config: QuantumCountryConfig,
    result: DashboardResourcesResult,
) -> list[QuantumDashboardConfig]:
    existing_by_id = {dashboard.dashboard_id: dashboard for dashboard in country_config.dashboards}
    default_dashboard = country_config.default_dashboard()
    default_id = default_dashboard.dashboard_id if default_dashboard else None
    dashboards = list(country_config.dashboards)
    for resource in result.resources:
        existing = existing_by_id.get(resource.dashboard_id)
        fallback_team_id = (existing.team_id if existing else "") or country_config.team_id
        is_default = resource.dashboard_id == default_id or (
            default_id is None and resource.starred
        )
        dashboard = _dashboard_from_resource(
            resource.model_copy(update={"team_id": resource.team_id or fallback_team_id}),
            is_default=is_default,
        )
        dashboards = _upsert_dashboard(
            dashboards,
            dashboard.model_copy(
                update={
                    "widgets": existing.widgets if existing else [],
                    "tabs": existing.tabs if existing else [],
                    "validated": True,
                    "validation_status": "ok",
                }
            ),
        )
    return dashboards


def _dashboard_by_id(
    country_config: QuantumCountryConfig,
    dashboard_id: str,
) -> QuantumDashboardConfig | None:
    return next(
        (
            dashboard
            for dashboard in country_config.dashboards
            if dashboard.dashboard_id == dashboard_id
        ),
        None,
    )


def _structure_tab_index(
    structure_role: str,
    fallback: int,
    tabs: Sequence[object],
) -> int:
    for tab in tabs:
        normalized_role = getattr(tab, "normalized_role", None)
        tab_index = getattr(tab, "tab_index", fallback)
        if normalized_role == structure_role:
            return _int(tab_index)
    return fallback


def _int(value: object) -> int:
    if not isinstance(value, int | float | str):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


@router.get("/health")
def health() -> dict[str, str | int]:
    return {
        "status": "ok",
        "app": APP_ID,
        "name": APP_NAME,
        "api_schema": API_SCHEMA_VERSION,
        "pid": os.getpid(),
    }


@router.get("/config/quantum", response_model=QuantumPublicConfig)
def get_quantum_config(
    store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
) -> QuantumPublicConfig:
    return public_quantum_config(store.read())


@router.put("/config/quantum", response_model=QuantumPublicConfig)
def put_quantum_config(
    update: QuantumPublicConfigUpdate,
    store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
) -> QuantumPublicConfig:
    secret_store.set_manual_cookie(update.manual_cookie)
    merged = merge_public_quantum_update(store.read(), update)
    _validate_default_dashboards(merged)
    return public_quantum_config(store.write(merged))


@router.get("/quantum/countries/{country}/dashboards")
def list_country_quantum_dashboards(
    country: str,
    store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
) -> dict[str, object]:
    config = store.read()
    country_config = config.required_country_config(country)
    result = read_dashboard_resources_cache(country_config.country)
    if result is None:
        result = resources_from_dashboard_configs(
            country_config.dashboards,
            country=country_config.country,
        )
    return {
        "country": country_config.country.value,
        "total_count": result.total_count,
        "from_cache": result.from_cache,
        "fetched_at": result.fetched_at.isoformat(),
        "dashboards": [dashboard.model_dump(mode="json") for dashboard in result.resources],
        "source": "dashboard_resources_cache" if result.from_cache else "quantum_graphql",
        "warning": result.warning,
    }


@router.post("/quantum/countries/{country}/dashboards/refresh")
def refresh_country_quantum_dashboards(
    country: str,
    store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    settings: Annotated[Settings, Depends(settings_dep)],
    cookie_provider: Annotated[BrowserCookieProvider, Depends(cookie_provider_dep)],
) -> dict[str, object]:
    config = store.read()
    country_config = config.required_country_config(country)
    cookies = _cookies_for_quantum(config, country_config, cookie_provider)
    discovered, error = discover_dashboards_via_browser(
        settings=settings,
        cookies=cookies,
        country=country_config.country,
        base_url=country_config.base_url or settings.quantum_default_base_url,
        wait_seconds=settings.quantum_capture_timeout_seconds,
        session_mode=config.session_mode.value,
    )
    cached_result = read_dashboard_resources_cache(country_config.country)
    if discovered:
        result = result_from_resource_rows(
            [_resource_from_summary(summary) for summary in discovered],
            country=country_config.country,
            fetched_at=datetime.now(UTC),
        )
        write_dashboard_resources_cache(result)
    elif cached_result is not None:
        result = cached_result.model_copy(
            update={
                "warning": error
                or "No se pudo descubrir dashboards en Quantum Web; se conserva cache local."
            }
        )
    else:
        cached = dashboards_from_config_cache(country_config)
        result = result_from_resource_rows(
            [_resource_from_summary(summary, source="cache") for summary in cached],
            country=country_config.country,
            fetched_at=datetime.now(UTC),
            from_cache=True,
        )
    if not result.resources:
        detail = error or "No se encontraron dashboards en Quantum Web ni en cache local."
        raise HTTPException(status_code=400, detail=detail)
    updated_countries = [
        item.model_copy(
            update={
                "dashboards": _merge_dashboard_resources(
                    item,
                    result,
                )
            }
        )
        if item.country == country_config.country
        else item
        for item in config.countries
    ]
    _write_config(store, config, updated_countries)
    return {
        "country": country_config.country.value,
        "total_count": result.total_count,
        "from_cache": result.from_cache,
        "dashboards": [resource.model_dump(mode="json") for resource in result.resources],
        "source": "quantum_graphql" if discovered else "cache",
        "warning": error
        if discovered
        else (error or "No se pudo descubrir dashboards en Quantum Web; se conserva cache local."),
    }


@router.post("/quantum/countries/{country}/dashboards/discover")
def discover_country_quantum_dashboards(
    country: str,
    store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    settings: Annotated[Settings, Depends(settings_dep)],
    cookie_provider: Annotated[BrowserCookieProvider, Depends(cookie_provider_dep)],
) -> dict[str, object]:
    return refresh_country_quantum_dashboards(country, store, settings, cookie_provider)


@router.post("/quantum/countries/{country}/dashboards/manual")
def add_manual_quantum_dashboard(
    country: str,
    request: ManualDashboardRequest,
    store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    settings: Annotated[Settings, Depends(settings_dep)],
    cookie_provider: Annotated[BrowserCookieProvider, Depends(cookie_provider_dep)],
) -> dict[str, object]:
    config = store.read()
    country_config = config.required_country_config(country)
    manual = manual_dashboard_input_from_request(
        request,
        fallback_base_url=country_config.base_url or settings.quantum_default_base_url,
    )
    cookies = _cookies_for_quantum(config, country_config, cookie_provider)
    structure, error = discover_dashboard_structure_via_browser(
        settings=settings,
        cookies=cookies,
        country=country_config.country,
        base_url=manual.base_url or country_config.base_url or settings.quantum_default_base_url,
        dashboard_id=manual.dashboard_id,
        team_id=manual.team_id or country_config.team_id or None,
        wait_seconds=settings.quantum_capture_timeout_seconds,
        session_mode=config.session_mode.value,
    )
    if not structure.tabs and not structure.widgets:
        detail = error or "No se pudo validar el dashboard manual contra Quantum."
        raise HTTPException(status_code=400, detail=detail)
    existing = _dashboard_by_id(country_config, manual.dashboard_id)
    existing_name = existing.name if existing else ""
    dashboard = QuantumDashboardConfig(
        dashboard_id=manual.dashboard_id,
        name=manual.name or structure.dashboard_name or existing_name,
        dashboard_type="DASHBOARD",
        team_id=manual.team_id or structure.team_id or (existing.team_id if existing else ""),
        summary_tab=_structure_tab_index(
            "summary",
            existing.summary_tab if existing else 0,
            structure.tabs,
        ),
        errors_tab=_structure_tab_index(
            "errors",
            existing.errors_tab if existing else 1,
            structure.tabs,
        ),
        is_default=existing.is_default if existing else False,
        is_manual=True,
        validated=True,
        validation_status="ok",
        source="manual",
        discovered_at=structure.discovered_at,
        last_structure_at=structure.discovered_at,
        tabs=tab_configs_from_structure(structure),
        widgets=widget_configs_from_structure(structure, existing.widgets if existing else []),
    )
    updated_countries = [
        item.model_copy(update={"dashboards": _upsert_dashboard(item.dashboards, dashboard)})
        if item.country == country_config.country
        else item
        for item in config.countries
    ]
    _write_config(store, config, updated_countries)
    cached = read_dashboard_resources_cache(country_config.country)
    resource = QuantumDashboardResource(
        dashboard_id=dashboard.dashboard_id,
        name=dashboard.name,
        type="DASHBOARD",
        starred=dashboard.is_default,
        country=country_config.country,
        team_id=dashboard.team_id or None,
        source="manual",
        order=len(cached.resources) if cached else len(country_config.dashboards),
        discovered_at=dashboard.discovered_at or datetime.now(UTC),
    )
    write_dashboard_resources_cache(
        result_from_resource_rows(
            [*(cached.resources if cached else []), resource],
            country=country_config.country,
            fetched_at=datetime.now(UTC),
            from_cache=True,
        )
    )
    return {
        "country": country_config.country.value,
        "dashboard": dashboard.model_dump(mode="json"),
        "structure": structure.model_dump(mode="json"),
        "warning": error,
    }


@router.post("/quantum/countries/{country}/dashboards/{dashboard_id}/structure/discover")
def discover_quantum_dashboard_structure(
    country: str,
    dashboard_id: str,
    store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    settings: Annotated[Settings, Depends(settings_dep)],
    cookie_provider: Annotated[BrowserCookieProvider, Depends(cookie_provider_dep)],
) -> dict[str, object]:
    config = store.read()
    country_config = config.required_country_config(country)
    dashboard = _dashboard_by_id(country_config, dashboard_id)
    if dashboard is None:
        raise HTTPException(status_code=404, detail="Dashboard is not configured for this country.")
    cookies = _cookies_for_quantum(config, country_config, cookie_provider)
    structure, error = discover_dashboard_structure_via_browser(
        settings=settings,
        cookies=cookies,
        country=country_config.country,
        base_url=country_config.base_url or settings.quantum_default_base_url,
        dashboard_id=dashboard.dashboard_id,
        team_id=dashboard.team_id or country_config.team_id or None,
        wait_seconds=settings.quantum_capture_timeout_seconds,
        session_mode=config.session_mode.value,
    )
    if not structure.tabs and not structure.widgets:
        cached = structure_from_dashboard_config(country_config.country, dashboard)
        if not cached.tabs and not cached.widgets:
            detail = error or "No se pudo leer la estructura real del dashboard en Quantum Web."
            raise HTTPException(status_code=400, detail=detail)
        payload = cached.model_dump(mode="json")
        payload["warning"] = error or "Se conserva la ultima estructura real guardada."
        return payload
    dashboard_with_structure = dashboard.model_copy(
        update={
            "name": structure.dashboard_name or dashboard.name,
            "summary_tab": _structure_tab_index(
                "summary",
                dashboard.summary_tab,
                structure.tabs,
            ),
            "errors_tab": _structure_tab_index(
                "errors",
                dashboard.errors_tab,
                structure.tabs,
            ),
            "tabs": tab_configs_from_structure(structure),
            "widgets": widget_configs_from_structure(structure, dashboard.widgets),
            "last_structure_at": structure.discovered_at,
            "source": structure.source,
        }
    )
    updated_countries = [
        item.model_copy(
            update={"dashboards": _upsert_dashboard(item.dashboards, dashboard_with_structure)}
        )
        if item.country == country_config.country
        else item
        for item in config.countries
    ]
    _write_config(store, config, updated_countries)
    payload = structure.model_dump(mode="json")
    payload["warning"] = error
    return payload


@router.post("/quantum/test-connection")
def test_connection(
    store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    cookie_provider: Annotated[BrowserCookieProvider, Depends(cookie_provider_dep)],
    settings: Annotated[Settings, Depends(settings_dep)],
    country: str | None = None,
) -> dict[str, object]:
    config = store.read()
    try:
        country_config = config.required_country_config(country)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not country_config.base_url:
        raise HTTPException(status_code=400, detail="Selected country needs a base URL.")
    if config.session_mode == "manual":
        manual_cookie = secret_store.get_manual_cookie()
        if not manual_cookie:
            raise HTTPException(status_code=400, detail="Manual cookie is not available in memory.")
        cookies = cookie_provider.from_manual_header(manual_cookie, str(country_config.base_url))
    elif config.session_mode == "controlled":
        cookies = []
    else:
        cookies = cookie_provider.load(config.browser.value, str(country_config.base_url))
    return (
        QuantumClient(settings, config, cookie_provider, cookies)
        .test_connection()
        .model_dump(mode="json")
    )


@router.post("/quantum/validate-access")
def validate_access(
    store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    settings: Annotated[Settings, Depends(settings_dep)],
) -> dict[str, object]:
    config = store.read()
    country_config = config.required_country_config()
    discovery = discover_dashboard_from_config(settings=settings, country_config=country_config)
    ok = bool(discovery.base_url and discovery.dashboard_id and discovery.tabs)
    return {
        "status": "ok" if ok else "ko",
        "message": "Dashboard, team and tabs resolved." if ok else discovery.message,
        "details": discovery.model_dump(mode="json"),
    }


@router.post("/ingestions")
async def create_ingestion(
    request: IngestionCreate,
    service: Annotated[IngestionService, Depends(ingestion_service_dep)],
) -> dict[str, object]:
    return service.start(request).model_dump(mode="json")


@router.post("/ingestions/missing-days")
async def create_missing_days_ingestion(
    request: MissingDaysIngestionCreate,
    service: Annotated[IngestionService, Depends(ingestion_service_dep)],
) -> dict[str, object]:
    try:
        job = service.start_missing_days(
            IngestionCreate(
                country=request.country,
                days=request.days,
                range_key=request.range_key,
                start_date=request.start_date,
                end_date=request.end_date,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return job.model_dump(mode="json")


@router.post("/ingestions/range")
async def create_range_ingestion(
    request: RangeIngestionCreate,
    service: Annotated[IngestionService, Depends(ingestion_service_dep)],
) -> dict[str, object]:
    job = service.start(
        IngestionCreate(
            country=request.country,
            range_key=request.range_key,
            start_date=request.start_date,
            end_date=request.end_date,
        )
    )
    payload = job.model_dump(mode="json")
    payload["reason"] = request.reason
    return payload


@router.get("/ingestions")
def list_ingestions(
    service: Annotated[IngestionService, Depends(ingestion_service_dep)],
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
) -> dict[str, object]:
    active = [job.model_dump(mode="json") for job in service.list()]
    persisted = store.list_ingestions()
    return {"active": active, "history": persisted, "persisted": persisted}


@router.get("/ingestions/{ingestion_id}")
def get_ingestion(
    ingestion_id: str,
    service: Annotated[IngestionService, Depends(ingestion_service_dep)],
) -> dict[str, object]:
    job = service.get(ingestion_id)
    if not job:
        raise HTTPException(status_code=404, detail="Ingestion not found.")
    return job.model_dump(mode="json")


@router.post("/ingestions/{ingestion_id}/cancel")
def cancel_ingestion(
    ingestion_id: str,
    service: Annotated[IngestionService, Depends(ingestion_service_dep)],
) -> dict[str, object]:
    job = service.cancel(ingestion_id)
    if not job:
        raise HTTPException(status_code=404, detail="Ingestion not found.")
    return job.model_dump(mode="json")


@router.get("/datasets")
def datasets(store: Annotated[ParquetStore, Depends(parquet_store_dep)]) -> dict[str, object]:
    payload = AnalyticsService(store).datasets()
    payload["data_dir"] = str(store.settings.qm_data_dir)
    legacy = Path("data")
    payload["legacy_data_detected"] = (
        legacy.exists() and legacy.resolve() != store.settings.qm_data_dir.resolve()
    )
    return payload


@router.post("/datasets/migrate-legacy-data")
def migrate_legacy_data(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
) -> dict[str, object]:
    legacy = Path("data")
    if not legacy.exists() or legacy.resolve() == store.settings.qm_data_dir.resolve():
        raise HTTPException(status_code=404, detail="No legacy ./data folder detected.")
    return store.migrate_legacy_data(legacy)


@router.post("/datasets/{country}/regenerate-derived")
def regenerate_derived(
    country: str,
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    dashboard_id: str | None = None,
    range_key: str = "today",
) -> dict[str, object]:
    return build_derived_datasets(
        store,
        country,
        dashboard_id=dashboard_id,
        range_key=range_key,
    ).model_dump(mode="json")


@router.post("/datasets/{country}/regression")
def run_dataset_regression(
    country: str,
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    dashboard_id: str | None = None,
    range_key: str = "today",
) -> dict[str, object]:
    return run_regression(
        store, country, dashboard_id=dashboard_id, range_key=range_key
    ).model_dump(mode="json")


@router.delete("/datasets/{country}")
def delete_dataset(
    country: str,
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    confirm: str | None = None,
) -> dict[str, object]:
    if confirm != country:
        raise HTTPException(
            status_code=400,
            detail="Dataset deletion requires confirm=<country>.",
        )
    return {"deleted": store.delete_country(country)}


@router.get("/datasets/{country}/entities")
def dataset_entities(
    country: str,
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    dashboard_id: str | None = None,
) -> dict[str, object]:
    return {
        "country": country,
        "dashboard_id": dashboard_id,
        "entities": store.list_country_entities(country, dashboard_id=dashboard_id),
    }


@router.get("/datasets/{country}/dashboards")
def dataset_dashboards(
    country: str,
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
) -> dict[str, object]:
    dashboards: dict[str, dict[str, object]] = {}
    for entity in store.list_country_entities(country):
        dashboard_id = entity.get("dashboard_id")
        if not dashboard_id:
            continue
        row = dashboards.setdefault(
            str(dashboard_id),
            {
                "dashboard_id": dashboard_id,
                "dashboard_name": entity.get("dashboard_name"),
                "entities": 0,
                "rows": 0,
                "bytes": 0,
            },
        )
        row["entities"] = _int(row["entities"]) + 1
        row["rows"] = _int(row["rows"]) + _int(entity.get("rows"))
        row["bytes"] = _int(row["bytes"]) + _int(entity.get("bytes"))
    return {"country": country, "dashboards": list(dashboards.values())}


@router.get("/datasets/{country}/evidence")
def dataset_evidence(
    country: str,
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
) -> dict[str, object]:
    evidence = build_evidence_report(store, country)
    return {
        "country": country,
        "evidence": [item.model_dump(mode="json") for item in evidence],
    }


@router.get("/datasets/{country}/entities/{entity:path}/schema")
def dataset_entity_schema(
    country: str,
    entity: str,
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
) -> dict[str, object]:
    page = store.read_country_entity_page(country, entity, limit=1)
    return {
        "country": country,
        "entity": entity,
        "schema": store.country_entity_schema(country, entity),
        "rows": page["total"],
    }


@router.get("/datasets/{country}/entities/{entity:path}")
def dataset_entity_rows(
    country: str,
    entity: str,
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    dashboard_id: str | None = None,
    widget_id: str | None = None,
    search: str | None = None,
    sort: str | None = None,
    direction: SortDirection = "asc",
    offset: int = 0,
    limit: int = 100,
) -> dict[str, object]:
    page = store.read_country_entity_page(
        country,
        entity,
        dashboard_id=dashboard_id,
        widget_id=widget_id,
        search=search,
        sort=sort,
        direction=direction,
        offset=offset,
        limit=limit,
    )
    return {
        "country": country,
        "entity": entity,
        "rows": page["rows"],
        "columns": page["columns"],
        "total": page["total"],
        "offset": page["offset"],
        "limit": page["limit"],
        "source": "parquet",
    }


@router.post("/datasets/export")
def export_datasets(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    config_store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    payload: Annotated[DatasetExportRequest | list[str] | None, Body()] = None,
) -> dict[str, object]:
    if isinstance(payload, list):
        request = DatasetExportRequest(countries=[str(item) for item in payload])
    else:
        request = payload or DatasetExportRequest()
    countries = request.countries or [row["country"] for row in store.list_datasets()]
    configured_export_path = config_store.read().export_path
    export_path = request.export_path or configured_export_path
    target_dir = Path(export_path).expanduser() if export_path else None
    path = store.export_countries(countries, target_dir=target_dir)
    return {
        "status": "exported",
        "path": str(path),
        "filename": path.name,
        "size_bytes": path.stat().st_size,
    }


@router.get("/datasets/exports/latest")
def latest_dataset_export(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
) -> dict[str, object]:
    latest = store.latest_export()
    return latest or {"status": "empty"}


@router.post("/datasets/import")
async def import_datasets(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    file: Annotated[UploadFile, File(...)],
) -> dict[str, object]:
    target = store.settings.exports_dir / f"import_{file.filename or 'dataset.zip'}"
    with target.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)
    return store.import_zip(target)


@router.get("/dashboards")
def dashboards(store: Annotated[ParquetStore, Depends(parquet_store_dep)]) -> dict[str, object]:
    summary = store.analytics_summary()
    return {"dashboards": [{"id": "local", "name": "Datos ingestados", "summary": summary}]}


@router.get("/dashboards/{dashboard_id}")
def dashboard(dashboard_id: str) -> dict[str, object]:
    return {"dashboard_id": dashboard_id, "source": "local-parquet"}


@router.get("/dashboards/{dashboard_id}/cards")
def dashboard_cards(
    dashboard_id: str,
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
) -> dict[str, object]:
    _ = dashboard_id
    return {"cards": store.analytics_summary()}


@router.get("/cards/{card_id}/data")
def card_data(
    card_id: str, store: Annotated[ParquetStore, Depends(parquet_store_dep)]
) -> dict[str, object]:
    return {"card_id": card_id, "rows": store.card_data(card_id)}


@router.get("/analytics/summary")
def analytics_summary(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
) -> dict[str, object]:
    return AnalyticsService(store).summary()


@router.get("/analytics/countries")
def analytics_countries(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
) -> dict[str, object]:
    return AnalyticsService(store).countries()


@router.get("/analytics/dashboard/summary")
def analytics_dashboard_summary(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    country: str = "MX",
    dimension: str | None = None,
    segment: str | None = None,
) -> dict[str, object]:
    return AnalyticsService(store).dashboard_summary(country, dimension, segment)


@router.get("/analytics/dashboard/summary/table")
def analytics_dashboard_summary_table(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    country: str = "MX",
    search: str | None = None,
    sort: str = "page_views",
    direction: SortDirection = "desc",
    dimension: str | None = None,
    segment: str | None = None,
) -> dict[str, object]:
    return AnalyticsService(store).dashboard_summary_table(
        country=country,
        search=search,
        sort=sort,
        direction=direction,
        dimension=dimension,
        segment=segment,
    )


@router.get("/analytics/dashboard/errors")
def analytics_dashboard_errors(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    country: str = "MX",
    dimension: str | None = None,
    segment: str | None = None,
) -> dict[str, object]:
    return AnalyticsService(store).dashboard_errors(country, dimension, segment)


@router.get("/analytics/dashboard/errors/table")
def analytics_dashboard_errors_table(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    country: str = "MX",
    search: str | None = None,
    sort: str = "error_session_percent",
    direction: SortDirection = "desc",
    dimension: str | None = None,
    segment: str | None = None,
) -> dict[str, object]:
    return AnalyticsService(store).dashboard_errors_table(
        country=country,
        search=search,
        sort=sort,
        direction=direction,
        dimension=dimension,
        segment=segment,
    )


@router.get("/local-dashboard/countries")
def local_dashboard_countries(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    config_store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
) -> dict[str, object]:
    return LocalDashboardService(store, config_store).countries()


@router.get("/local-dashboard/status")
def local_dashboard_status(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    config_store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    country: str = "MX",
    range_key: str = "last_7_days",
    dashboard_id: str | None = None,
) -> dict[str, object]:
    return LocalDashboardService(store, config_store).status(
        country, range_key=range_key, dashboard_id=dashboard_id
    )


@router.get("/local-dashboard/coverage")
def local_dashboard_coverage(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    country: str = "MX",
    start: str | None = None,
    end: str | None = None,
    range_key: str = "last_7_days",
    dashboard_id: str | None = None,
) -> dict[str, object]:
    try:
        resolution = resolve_range(
            store,
            country,
            range_key=range_key,
            start=start,
            end=end,
            timezone="CST",
            last_regression_status=LocalDashboardService(store, config_store=None)
            .status(country, range_key=range_key, dashboard_id=dashboard_id)
            .get("regression_status"),
        )
        return range_resolution_payload(resolution)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/local-dashboard/summary")
def local_dashboard_summary(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    config_store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    country: str = "MX",
    start_date: str | None = None,
    end_date: str | None = None,
    range_key: str = "last_7_days",
    dashboard_id: str | None = None,
) -> dict[str, object]:
    return LocalDashboardService(store, config_store).summary(
        country,
        start_date=start_date,
        end_date=end_date,
        range_key=range_key,
        dashboard_id=dashboard_id,
    )


@router.get("/local-dashboard/summary/table")
def local_dashboard_summary_table(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    config_store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    country: str = "MX",
    search: str | None = None,
    sort: str = "page_views",
    direction: SortDirection = "desc",
    start_date: str | None = None,
    end_date: str | None = None,
    range_key: str = "last_7_days",
    dashboard_id: str | None = None,
) -> dict[str, object]:
    return LocalDashboardService(store, config_store).summary_table(
        country,
        search=search,
        sort=sort,
        direction=direction,
        start_date=start_date,
        end_date=end_date,
        range_key=range_key,
        dashboard_id=dashboard_id,
    )


@router.get("/local-dashboard/errors")
def local_dashboard_errors(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    config_store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    country: str = "MX",
    start_date: str | None = None,
    end_date: str | None = None,
    range_key: str = "last_7_days",
    dashboard_id: str | None = None,
) -> dict[str, object]:
    return LocalDashboardService(store, config_store).errors(
        country,
        start_date=start_date,
        end_date=end_date,
        range_key=range_key,
        dashboard_id=dashboard_id,
    )


@router.get("/local-dashboard/errors/top-errors")
def local_dashboard_top_errors(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    config_store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    country: str = "MX",
    search: str | None = None,
    sort: str = "error_sessions",
    direction: SortDirection = "desc",
    start_date: str | None = None,
    end_date: str | None = None,
    range_key: str = "last_7_days",
    dashboard_id: str | None = None,
) -> dict[str, object]:
    return LocalDashboardService(store, config_store).top_errors_table(
        country,
        search=search,
        sort=sort,
        direction=direction,
        start_date=start_date,
        end_date=end_date,
        range_key=range_key,
        dashboard_id=dashboard_id,
    )


@router.get("/local-dashboard/errors/app-name")
def local_dashboard_error_app_name(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    config_store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    country: str = "MX",
    search: str | None = None,
    sort: str = "row_index",
    direction: SortDirection = "asc",
    start_date: str | None = None,
    end_date: str | None = None,
    range_key: str = "last_7_days",
    dashboard_id: str | None = None,
) -> dict[str, object]:
    return LocalDashboardService(store, config_store).app_name_error_table(
        country,
        search=search,
        sort=sort,
        direction=direction,
        start_date=start_date,
        end_date=end_date,
        range_key=range_key,
        dashboard_id=dashboard_id,
    )


@router.get("/local-dashboard/cards/{card_role}/detail")
def local_dashboard_card_detail(
    card_role: str,
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    config_store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    country: str = "MX",
    start_date: str | None = None,
    end_date: str | None = None,
    range_key: str = "last_7_days",
    dashboard_id: str | None = None,
) -> dict[str, object]:
    return LocalDashboardService(store, config_store).card_detail(
        country,
        card_role,
        start_date=start_date,
        end_date=end_date,
        range_key=range_key,
        dashboard_id=dashboard_id,
    )


@router.get("/local-dashboard/cards/{card_role}/breakdown")
def local_dashboard_card_breakdown(
    card_role: str,
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    config_store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    country: str = "MX",
    range_key: str = "last_7_days",
    dashboard_id: str | None = None,
) -> dict[str, object]:
    return LocalDashboardService(store, config_store).card_breakdown(
        country, card_role, range_key=range_key, dashboard_id=dashboard_id
    )


@router.get("/local-dashboard/cards/{card_role}/points")
def local_dashboard_card_points(
    card_role: str,
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    config_store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    country: str = "MX",
    range_key: str = "last_7_days",
    dashboard_id: str | None = None,
) -> dict[str, object]:
    return LocalDashboardService(store, config_store).card_points(
        country, card_role, range_key=range_key, dashboard_id=dashboard_id
    )


@router.get("/analytics/timeseries")
def analytics_timeseries(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
) -> dict[str, object]:
    return AnalyticsService(store).timeseries()


@router.get("/analytics/table")
def analytics_table(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
) -> dict[str, object]:
    return AnalyticsService(store).table()


@router.get("/analytics/filters")
def analytics_filters(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
) -> dict[str, object]:
    return AnalyticsService(store).filters()
