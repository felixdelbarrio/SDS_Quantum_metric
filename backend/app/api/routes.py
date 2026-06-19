from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, cast

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.app.analytics.models import SortDirection
from backend.app.analytics.service import AnalyticsService
from backend.app.auth.browser_cookies import BrowserCookieProvider
from backend.app.auth.session_store import secret_store
from backend.app.config.settings import Settings, get_settings
from backend.app.ingestion.models import IngestionCreate, MissingDaysIngestionCreate
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
    WidgetType,
    merge_public_quantum_update,
    public_quantum_config,
)
from backend.app.quantum_dashboard.builder import build_derived_datasets
from backend.app.quantum_dashboard.catalog import MANDATORY_CARDS
from backend.app.quantum_dashboard.discovery import discover_dashboard_from_config
from backend.app.quantum_dashboard.evidence import build_evidence_report
from backend.app.quantum_dashboard.models import DashboardDiscoveryResult
from backend.app.quantum_dashboard.range_query import range_resolution_payload, resolve_range
from backend.app.quantum_dashboard.regression import run_regression
from backend.app.quantum_dashboard.service import LocalDashboardService
from backend.app.runtime import API_SCHEMA_VERSION, APP_ID, APP_NAME
from backend.app.storage.parquet_store import ParquetStore

router = APIRouter(prefix="/api")
_INGESTION_SERVICE: IngestionService | None = None


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


def _dashboard_from_discovery(
    discovery: DashboardDiscoveryResult,
    *,
    manual: bool,
) -> QuantumDashboardConfig:
    discovered_at = datetime.now(UTC)
    dashboard_id = str(discovery.dashboard_id or "")
    return QuantumDashboardConfig(
        dashboard_id=dashboard_id,
        name="Dashboard manual" if manual else "Dashboard default",
        dashboard_type="Quantum dashboard",
        team_id=str(discovery.team_id or ""),
        summary_tab=int(discovery.summary_tab or 0),
        errors_tab=int(discovery.errors_tab or 1),
        is_default=not manual,
        is_manual=manual,
        validated=bool(dashboard_id),
        validation_status="ok" if dashboard_id else "ko",
        discovered_at=discovered_at,
        widgets=[
            QuantumWidgetConfig(
                role=spec.role,
                title=spec.title,
                widget_id=f"role:{spec.role}",
                widget_type=cast(
                    WidgetType,
                    "DONUT" if spec.card_type == "DONUT" else spec.card_type,
                ),
                tab=spec.tab,
                enabled=True,
                discovered_at=discovered_at,
            )
            for spec in MANDATORY_CARDS
        ],
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
            merged_widgets = [
                widget.model_copy(
                    update={
                        "enabled": widgets_by_role.get(widget.role, widget).enabled,
                        "widget_id": widgets_by_role.get(widget.role, widget).widget_id
                        or widget.widget_id,
                    }
                )
                for widget in dashboard.widgets
            ]
            next_dashboards.append(
                dashboard.model_copy(
                    update={
                        "widgets": merged_widgets,
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
    if next_dashboards and not any(item.is_default for item in next_dashboards):
        next_dashboards[0] = next_dashboards[0].model_copy(update={"is_default": True})
    return next_dashboards


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
    return public_quantum_config(store.write(merged))


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


@router.post("/quantum/discover-dashboard")
def discover_dashboard(
    store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    settings: Annotated[Settings, Depends(settings_dep)],
    country: str | None = None,
    dashboard_id: str | None = None,
    manual: bool = False,
) -> dict[str, object]:
    config = store.read()
    country_config = config.required_country_config(country)
    discovery_country = country_config
    if dashboard_id:
        discovery_country = country_config.model_copy(update={"dashboard_id": dashboard_id})
    discovery = discover_dashboard_from_config(settings=settings, country_config=discovery_country)
    if discovery.dashboard_id:
        updated_countries = []
        for item in config.countries:
            if item.country == country_config.country:
                dashboard = _dashboard_from_discovery(
                    discovery, manual=manual or bool(dashboard_id)
                )
                updated_countries.append(
                    item.model_copy(
                        update={
                            "base_url": discovery.base_url,
                            "dashboard_id": dashboard.dashboard_id,
                            "team_id": dashboard.team_id,
                            "tab": dashboard.summary_tab,
                            "dashboards": _upsert_dashboard(item.dashboards, dashboard),
                        }
                    )
                )
            else:
                updated_countries.append(item)
        _write_config(store, config, updated_countries)
    return discovery.model_dump(mode="json")


@router.post("/quantum/test-dashboard")
def test_dashboard(
    store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    settings: Annotated[Settings, Depends(settings_dep)],
    country: str,
    dashboard_id: str,
) -> dict[str, object]:
    return discover_dashboard(
        store=store,
        settings=settings,
        country=country,
        dashboard_id=dashboard_id,
        manual=True,
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
) -> dict[str, object]:
    return build_derived_datasets(store, country).model_dump(mode="json")


@router.post("/datasets/{country}/regression")
def run_dataset_regression(
    country: str,
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
) -> dict[str, object]:
    return run_regression(store, country).model_dump(mode="json")


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
) -> dict[str, object]:
    return {"country": country, "entities": store.list_country_entities(country)}


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
    search: str | None = None,
    sort: str | None = None,
    direction: SortDirection = "asc",
    offset: int = 0,
    limit: int = 100,
) -> dict[str, object]:
    page = store.read_country_entity_page(
        country,
        entity,
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
    range_key: str = "today",
) -> dict[str, object]:
    return LocalDashboardService(store, config_store).status(country, range_key=range_key)


@router.get("/local-dashboard/coverage")
def local_dashboard_coverage(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    country: str = "MX",
    start: str | None = None,
    end: str | None = None,
    range_key: str = "custom",
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
            .status(country, range_key=range_key)
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
    dimension: str | None = None,
    segment: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    range_key: str = "today",
) -> dict[str, object]:
    return LocalDashboardService(store, config_store).summary(
        country,
        dimension=dimension,
        segment=segment,
        start_date=start_date,
        end_date=end_date,
        range_key=range_key,
    )


@router.get("/local-dashboard/summary/table")
def local_dashboard_summary_table(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    config_store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    country: str = "MX",
    search: str | None = None,
    sort: str = "page_views",
    direction: SortDirection = "desc",
    dimension: str | None = None,
    segment: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    range_key: str = "today",
) -> dict[str, object]:
    return LocalDashboardService(store, config_store).summary_table(
        country,
        search=search,
        sort=sort,
        direction=direction,
        dimension=dimension,
        segment=segment,
        start_date=start_date,
        end_date=end_date,
        range_key=range_key,
    )


@router.get("/local-dashboard/errors")
def local_dashboard_errors(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    config_store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    country: str = "MX",
    dimension: str | None = None,
    segment: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    range_key: str = "today",
) -> dict[str, object]:
    return LocalDashboardService(store, config_store).errors(
        country,
        dimension=dimension,
        segment=segment,
        start_date=start_date,
        end_date=end_date,
        range_key=range_key,
    )


@router.get("/local-dashboard/errors/top-errors")
def local_dashboard_top_errors(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    config_store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    country: str = "MX",
    search: str | None = None,
    sort: str = "error_sessions",
    direction: SortDirection = "desc",
    dimension: str | None = None,
    segment: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    range_key: str = "today",
) -> dict[str, object]:
    return LocalDashboardService(store, config_store).top_errors_table(
        country,
        search=search,
        sort=sort,
        direction=direction,
        dimension=dimension,
        segment=segment,
        start_date=start_date,
        end_date=end_date,
        range_key=range_key,
    )


@router.get("/local-dashboard/errors/app-name")
def local_dashboard_error_app_name(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    config_store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    country: str = "MX",
    search: str | None = None,
    sort: str = "error_session_percent",
    direction: SortDirection = "desc",
    dimension: str | None = None,
    segment: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    range_key: str = "today",
) -> dict[str, object]:
    return LocalDashboardService(store, config_store).app_name_error_table(
        country,
        search=search,
        sort=sort,
        direction=direction,
        dimension=dimension,
        segment=segment,
        start_date=start_date,
        end_date=end_date,
        range_key=range_key,
    )


@router.get("/local-dashboard/cards/{card_role}/detail")
def local_dashboard_card_detail(
    card_role: str,
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    config_store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    country: str = "MX",
    start_date: str | None = None,
    end_date: str | None = None,
    range_key: str = "today",
) -> dict[str, object]:
    return LocalDashboardService(store, config_store).card_detail(
        country, card_role, start_date=start_date, end_date=end_date, range_key=range_key
    )


@router.get("/local-dashboard/cards/{card_role}/breakdown")
def local_dashboard_card_breakdown(
    card_role: str,
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    config_store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    country: str = "MX",
    range_key: str = "today",
) -> dict[str, object]:
    return LocalDashboardService(store, config_store).card_breakdown(
        country, card_role, range_key=range_key
    )


@router.get("/local-dashboard/cards/{card_role}/points")
def local_dashboard_card_points(
    card_role: str,
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    config_store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    country: str = "MX",
    range_key: str = "today",
) -> dict[str, object]:
    return LocalDashboardService(store, config_store).card_points(
        country, card_role, range_key=range_key
    )


@router.get("/analytics/dimensions")
def analytics_dimensions(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    country: str = "MX",
) -> dict[str, object]:
    return AnalyticsService(store).dimensions(country)


@router.get("/analytics/segments")
def analytics_segments(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    country: str = "MX",
) -> dict[str, object]:
    return AnalyticsService(store).segments(country)


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
