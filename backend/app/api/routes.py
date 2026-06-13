from __future__ import annotations

import shutil
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend.app.analytics.models import SortDirection
from backend.app.analytics.service import AnalyticsService
from backend.app.auth.browser_cookies import BrowserCookieProvider
from backend.app.auth.session_store import secret_store
from backend.app.config.settings import Settings, get_settings
from backend.app.ingestion.models import IngestionCreate
from backend.app.ingestion.service import IngestionService
from backend.app.quantum.client import QuantumClient
from backend.app.quantum.config_store import QuantumConfigStore
from backend.app.quantum.schemas import QuantumConfig, QuantumConfigUpdate
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


@router.get("/config/quantum", response_model=QuantumConfig)
def get_quantum_config(
    store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
) -> QuantumConfig:
    return store.read()


@router.put("/config/quantum", response_model=QuantumConfig)
def put_quantum_config(
    update: QuantumConfigUpdate,
    store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
) -> QuantumConfig:
    secret_store.set_manual_cookie(update.manual_cookie)
    return store.write(update)


@router.post("/quantum/test-connection")
def test_connection(
    store: Annotated[QuantumConfigStore, Depends(config_store_dep)],
    cookie_provider: Annotated[BrowserCookieProvider, Depends(cookie_provider_dep)],
    settings: Annotated[Settings, Depends(settings_dep)],
) -> dict[str, object]:
    config = store.read()
    if config.session_mode == "manual":
        manual_cookie = secret_store.get_manual_cookie()
        if not manual_cookie:
            raise HTTPException(status_code=400, detail="Manual cookie is not available in memory.")
        cookies = cookie_provider.from_manual_header(manual_cookie, str(config.base_url))
    else:
        cookies = cookie_provider.load(config.browser.value, str(config.base_url))
    return (
        QuantumClient(settings, config, cookie_provider, cookies)
        .test_connection()
        .model_dump(mode="json")
    )


@router.post("/ingestions")
async def create_ingestion(
    request: IngestionCreate,
    service: Annotated[IngestionService, Depends(ingestion_service_dep)],
) -> dict[str, object]:
    return service.start(request).model_dump(mode="json")


@router.get("/ingestions")
def list_ingestions(
    service: Annotated[IngestionService, Depends(ingestion_service_dep)],
    store: Annotated[ParquetStore, Depends(parquet_store_dep)],
) -> dict[str, object]:
    active = [job.model_dump(mode="json") for job in service.list()]
    persisted = store.list_ingestions()
    return {"active": active, "persisted": persisted}


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
    return {"datasets": store.list_datasets()}


@router.delete("/datasets/{country}")
def delete_dataset(
    country: str, store: Annotated[ParquetStore, Depends(parquet_store_dep)]
) -> dict[str, object]:
    return {"deleted": store.delete_country(country)}


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
