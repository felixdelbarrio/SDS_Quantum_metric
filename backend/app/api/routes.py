from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

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
    QuantumConfigUpdate,
    QuantumPublicConfig,
    QuantumPublicConfigUpdate,
    merge_public_quantum_update,
    public_quantum_config,
)
from backend.app.quantum_dashboard.builder import build_derived_datasets
from backend.app.quantum_dashboard.discovery import discover_dashboard_from_config
from backend.app.quantum_dashboard.regression import run_regression
from backend.app.quantum_dashboard.service import LocalDashboardService
from backend.app.storage.parquet_store import ParquetStore

router = APIRouter(prefix="/api")
_INGESTION_SERVICE: IngestionService | None = None


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


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
) -> dict[str, object]:
    config = store.read()
    country_config = config.required_country_config()
    discovery = discover_dashboard_from_config(settings=settings, country_config=country_config)
    if discovery.dashboard_id:
        updated_countries = []
        for item in config.countries:
            if item.country == country_config.country:
                updated_countries.append(
                    item.model_copy(
                        update={
                            "base_url": discovery.base_url,
                            "dashboard_id": discovery.dashboard_id or item.dashboard_id,
                            "team_id": discovery.team_id or item.team_id,
                            "tab": discovery.summary_tab,
                        }
                    )
                )
            else:
                updated_countries.append(item)
        store.write(
            QuantumConfigUpdate(
                browser=config.browser,
                session_mode=config.session_mode,
                country=config.country,
                countries=updated_countries,
                verify_tls=config.verify_tls,
            )
        )
    return discovery.model_dump(mode="json")


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
            IngestionCreate(country=request.country, days=request.days)
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
    countries: list[str],
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
) -> FileResponse:
    path = store.export_countries(countries)
    return FileResponse(path, filename=path.name, media_type="application/zip")


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
) -> dict[str, object]:
    return LocalDashboardService(store).countries()


@router.get("/local-dashboard/status")
def local_dashboard_status(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    country: str = "MX",
) -> dict[str, object]:
    return LocalDashboardService(store).status(country)


@router.get("/local-dashboard/coverage")
def local_dashboard_coverage(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    country: str = "MX",
    start: str | None = None,
    end: str | None = None,
) -> dict[str, object]:
    try:
        return store.day_coverage(country, start, end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/local-dashboard/summary")
def local_dashboard_summary(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    country: str = "MX",
    dimension: str | None = None,
    segment: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, object]:
    return LocalDashboardService(store).summary(
        country,
        dimension=dimension,
        segment=segment,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/local-dashboard/summary/table")
def local_dashboard_summary_table(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    country: str = "MX",
    search: str | None = None,
    sort: str = "page_views",
    direction: SortDirection = "desc",
    dimension: str | None = None,
    segment: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, object]:
    return LocalDashboardService(store).summary_table(
        country,
        search=search,
        sort=sort,
        direction=direction,
        dimension=dimension,
        segment=segment,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/local-dashboard/errors")
def local_dashboard_errors(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    country: str = "MX",
    dimension: str | None = None,
    segment: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, object]:
    return LocalDashboardService(store).errors(
        country,
        dimension=dimension,
        segment=segment,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/local-dashboard/errors/top-errors")
def local_dashboard_top_errors(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    country: str = "MX",
    search: str | None = None,
    sort: str = "error_sessions",
    direction: SortDirection = "desc",
    dimension: str | None = None,
    segment: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, object]:
    return LocalDashboardService(store).top_errors_table(
        country,
        search=search,
        sort=sort,
        direction=direction,
        dimension=dimension,
        segment=segment,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/local-dashboard/errors/app-name")
def local_dashboard_error_app_name(
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    country: str = "MX",
    search: str | None = None,
    sort: str = "error_session_percent",
    direction: SortDirection = "desc",
    dimension: str | None = None,
    segment: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, object]:
    return LocalDashboardService(store).app_name_error_table(
        country,
        search=search,
        sort=sort,
        direction=direction,
        dimension=dimension,
        segment=segment,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/local-dashboard/cards/{card_role}/detail")
def local_dashboard_card_detail(
    card_role: str,
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    country: str = "MX",
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, object]:
    return LocalDashboardService(store).card_detail(
        country, card_role, start_date=start_date, end_date=end_date
    )


@router.get("/local-dashboard/cards/{card_role}/breakdown")
def local_dashboard_card_breakdown(
    card_role: str,
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    country: str = "MX",
) -> dict[str, object]:
    return LocalDashboardService(store).card_breakdown(country, card_role)


@router.get("/local-dashboard/cards/{card_role}/points")
def local_dashboard_card_points(
    card_role: str,
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
    country: str = "MX",
) -> dict[str, object]:
    return LocalDashboardService(store).card_points(country, card_role)


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
