from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.config.defaults import DEFAULT_INGESTION_DEPTH_DAYS
from backend.app.quantum_dashboard.generic_roles import (
    generic_role_for_widget,
    is_generic_role,
    is_supported_generic_widget_type,
)


class BrowserName(StrEnum):
    chrome = "chrome"
    edge = "edge"
    safari = "safari"
    firefox = "firefox"


class SessionMode(StrEnum):
    browser = "browser"
    controlled = "controlled"
    manual = "manual"


class Country(StrEnum):
    ES = "ES"
    MX = "MX"
    CO = "CO"
    AR = "AR"
    PE = "PE"


COUNTRY_LABELS: dict[str, str] = {
    Country.ES.value: "Espana",
    Country.MX.value: "Mexico",
    Country.CO.value: "Colombia",
    Country.AR.value: "Argentina",
    Country.PE.value: "Peru",
}

COUNTRY_ORDER: tuple[Country, ...] = (
    Country.ES,
    Country.MX,
    Country.CO,
    Country.AR,
    Country.PE,
)

COUNTRY_TIMEZONES: dict[Country, str] = {
    Country.ES: "Europe/Madrid",
    Country.MX: "America/Mexico_City",
    Country.CO: "America/Bogota",
    Country.AR: "America/Argentina/Buenos_Aires",
    Country.PE: "America/Lima",
}


class CountryOption(BaseModel):
    code: Country
    label: str


def country_options() -> list[CountryOption]:
    return [
        CountryOption(code=country, label=COUNTRY_LABELS[country.value])
        for country in COUNTRY_ORDER
    ]


def country_label(country: str | Country) -> str:
    code = country.value if isinstance(country, Country) else country
    return COUNTRY_LABELS.get(code, code)


type WidgetSource = Literal["quantum_api", "quantum_web", "config_cache"]
type WidgetType = Literal["CHART", "TABLE", "DONUT", "KPI", "UNKNOWN"]


class QuantumDashboardTabConfig(BaseModel):
    tab_id: str | None = None
    tab_index: int = Field(default=0, ge=0)
    name: str
    normalized_role: str | None = None

    @field_validator("tab_id", "name", "normalized_role", mode="before")
    @classmethod
    def _strip_tab_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class QuantumDashboardSectionConfig(BaseModel):
    section_id: str | None = None
    tab_id: str | None = None
    tab_index: int = Field(default=0, ge=0)
    name: str
    section_index: int = Field(default=0, ge=0)

    @field_validator("section_id", "tab_id", "name", mode="before")
    @classmethod
    def _strip_section_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class QuantumWidgetConfig(BaseModel):
    role: str = ""
    title: str = ""
    widget_id: str = ""
    card_id: str | None = None
    widget_type: WidgetType = "UNKNOWN"
    tab_id: str | None = None
    tab: str = "unassigned"
    tab_name: str = "Sin pestaña"
    tab_index: int = Field(default=0, ge=0)
    tab_resolution: Literal["resolved", "unassigned", "ambiguous"] = "unassigned"
    section_id: str | None = None
    section_name: str | None = None
    section_index: int | None = Field(default=None, ge=0)
    widget_order: int | None = Field(default=None, ge=0)
    layout_x: int | None = None
    layout_y: int | None = None
    layout_width: int | None = Field(default=None, ge=1)
    layout_height: int | None = Field(default=None, ge=1)
    query_fingerprint: str | None = None
    visual_contract: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    required: bool = False
    supported: bool = True
    source: WidgetSource = "config_cache"
    discovered_at: datetime | None = None

    @field_validator(
        "role",
        "title",
        "widget_id",
        "card_id",
        "widget_type",
        "tab_id",
        "tab",
        "tab_name",
        "tab_resolution",
        "section_id",
        "section_name",
        "query_fingerprint",
        "source",
        mode="before",
    )
    @classmethod
    def _strip_widget_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _migrate_generic_widget_support(self) -> QuantumWidgetConfig:
        if self.role and is_generic_role(self.role):
            self.supported = True
            return self
        if not self.role and is_supported_generic_widget_type(self.widget_type):
            self.role = generic_role_for_widget(
                widget_id=self.widget_id,
                card_id=self.card_id,
                widget_type=self.widget_type,
                tab_index=self.tab_index,
            )
            self.supported = True
            self.required = True
            self.enabled = True
        return self


class QuantumDashboardConfig(BaseModel):
    dashboard_id: str = ""
    name: str = ""
    dashboard_type: str = "dashboard"
    team_id: str = ""
    summary_tab: int = Field(default=0, ge=0)
    errors_tab: int = Field(default=1, ge=0)
    timezone: str = ""
    is_default: bool = False
    is_manual: bool = False
    validated: bool = False
    validation_status: Literal["not_tested", "ok", "ko"] = "not_tested"
    source: Literal["quantum_api", "quantum_web", "config_cache", "manual"] = "config_cache"
    discovered_at: datetime | None = None
    last_structure_at: datetime | None = None
    tabs: list[QuantumDashboardTabConfig] = Field(default_factory=list)
    sections: list[QuantumDashboardSectionConfig] = Field(default_factory=list)
    widgets: list[QuantumWidgetConfig] = Field(default_factory=list)

    @field_validator(
        "dashboard_id", "name", "dashboard_type", "team_id", "timezone", "source", mode="before"
    )
    @classmethod
    def _strip_dashboard_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _seed_widgets(self) -> QuantumDashboardConfig:
        if _is_legacy_generated_dashboard_name(self.name, self.dashboard_id):
            self.name = ""
        if not self.tabs and self.widgets:
            self.tabs = _tabs_from_widgets(self.widgets)
        if self.widgets:
            self.widgets = [
                widget
                if widget.widget_order is not None
                else widget.model_copy(update={"widget_order": index})
                for index, widget in enumerate(self.widgets)
            ]
        return self

    def enabled_widget_roles(self) -> list[str]:
        return [
            widget.role
            for widget in self.widgets
            if widget.enabled and widget.supported and widget.role
        ]


class QuantumCountryConfig(BaseModel):
    country: Country
    base_url: str = ""
    timezone: str = ""
    dashboard_id: str = ""
    team_id: str = ""
    tab: int = Field(default=0, ge=0)
    enabled: bool = True
    dashboards: list[QuantumDashboardConfig] = Field(default_factory=list)

    @field_validator("base_url", "timezone", "dashboard_id", "team_id", mode="before")
    @classmethod
    def _strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _migrate_dashboard_fields(self) -> QuantumCountryConfig:
        if not self.timezone:
            self.timezone = COUNTRY_TIMEZONES[self.country]
        if not self.dashboards and self.dashboard_id:
            self.dashboards = [
                QuantumDashboardConfig(
                    dashboard_id=self.dashboard_id,
                    name="",
                    team_id=self.team_id,
                    summary_tab=self.tab,
                    errors_tab=1,
                    is_default=True,
                    validated=True,
                    validation_status="ok",
                )
            ]
        default_seen = False
        normalized: list[QuantumDashboardConfig] = []
        for dashboard in self.dashboards:
            next_dashboard = dashboard
            if not next_dashboard.timezone:
                next_dashboard = next_dashboard.model_copy(update={"timezone": self.timezone})
            if _is_legacy_generated_dashboard_name(dashboard.name, dashboard.dashboard_id):
                next_dashboard = next_dashboard.model_copy(update={"name": ""})
            if next_dashboard.is_default:
                if default_seen:
                    next_dashboard = next_dashboard.model_copy(update={"is_default": False})
                default_seen = True
            normalized.append(next_dashboard)
        self.dashboards = normalized
        for dashboard in self.dashboards:
            if dashboard.is_default:
                self.dashboard_id = dashboard.dashboard_id
                self.team_id = dashboard.team_id
                self.tab = dashboard.summary_tab
                break
        return self

    def is_ready_for_ingestion(self) -> bool:
        dashboard = self.default_dashboard()
        return bool(
            self.enabled
            and self.base_url
            and dashboard
            and dashboard.dashboard_id
            and dashboard.validated
        )

    def default_dashboard(self) -> QuantumDashboardConfig | None:
        return next((item for item in self.dashboards if item.is_default), None)

    def enabled_widget_roles(self) -> list[str]:
        dashboard = self.default_dashboard()
        if dashboard is None:
            return []
        return dashboard.enabled_widget_roles()

    def dashboard_url(self) -> str:
        dashboard = self.default_dashboard()
        dashboard_id = dashboard.dashboard_id if dashboard else self.dashboard_id
        team_id = dashboard.team_id if dashboard else self.team_id
        summary_tab = dashboard.summary_tab if dashboard else self.tab
        if not self.base_url or not dashboard_id:
            raise ValueError("Country config needs base_url and dashboard_id.")
        fragment_path = f"/dashboard/{dashboard_id}"
        query = urlencode(
            {
                "tab": summary_tab,
                **({"teamID": team_id} if team_id else {}),
            }
        )
        fragment = f"{fragment_path}?{query}" if query else fragment_path
        parsed = urlparse(self.base_url)
        base = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
        return f"{base.rstrip()}/#{fragment}"


class QuantumConfig(BaseModel):
    schema_version: int = 3
    browser: BrowserName = BrowserName.chrome
    session_mode: SessionMode = SessionMode.controlled
    country: Country = Country.MX
    countries: list[QuantumCountryConfig] = Field(default_factory=list)
    verify_tls: bool = True
    ingestion_depth_days: int = Field(default=DEFAULT_INGESTION_DEPTH_DAYS, ge=1, le=3650)
    theme_preference: Literal["system", "light", "dark"] = "system"
    export_path: str = ""

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_single_country(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        migrated = dict(value)
        migrated["schema_version"] = 3
        if value.get("countries"):
            return migrated

        country = value.get("country") or Country.MX.value
        dashboard_parts = _dashboard_parts(str(value.get("dashboard_url") or ""))
        legacy = QuantumCountryConfig(
            country=Country(country),
            base_url=str(value.get("base_url") or "https://bbvamx.quantummetric.com"),
            dashboard_id=str(dashboard_parts["dashboard_id"]),
            team_id=str(dashboard_parts["team_id"]),
            tab=int(dashboard_parts["tab"]),
        )
        migrated["countries"] = [legacy]
        migrated.pop("base_url", None)
        migrated.pop("dashboard_url", None)
        return migrated

    @model_validator(mode="after")
    def _ensure_country_is_configured(self) -> QuantumConfig:
        if not self.countries:
            self.countries = [
                QuantumCountryConfig(
                    country=Country.MX,
                    base_url="https://bbvamx.quantummetric.com",
                )
            ]
        if not any(item.country == self.country for item in self.countries):
            self.country = self.countries[0].country
        return self

    def country_config(self, country: Country | str | None = None) -> QuantumCountryConfig | None:
        target = Country(country or self.country)
        return next((item for item in self.countries if item.country == target), None)

    def required_country_config(self, country: Country | str | None = None) -> QuantumCountryConfig:
        config = self.country_config(country)
        if not config:
            raise ValueError(f"Country {country or self.country} is not configured.")
        return config


class QuantumConfigUpdate(QuantumConfig):
    manual_cookie: str | None = Field(default=None, exclude=True)


class QuantumPublicCountryConfig(BaseModel):
    country: Country
    base_url: str = ""
    timezone: str = ""
    enabled: bool = True
    is_default: bool = False
    dashboard_resolved: bool = False
    dashboards: list[QuantumDashboardConfig] = Field(default_factory=list)


class QuantumPublicConfig(BaseModel):
    browser: BrowserName = BrowserName.chrome
    session_mode: SessionMode = SessionMode.controlled
    country: Country = Country.MX
    countries: list[QuantumPublicCountryConfig] = Field(default_factory=list)
    verify_tls: bool = True
    ingestion_depth_days: int = Field(default=DEFAULT_INGESTION_DEPTH_DAYS, ge=1, le=3650)
    theme_preference: Literal["system", "light", "dark"] = "system"
    export_path: str = ""


class QuantumPublicConfigUpdate(QuantumPublicConfig):
    manual_cookie: str | None = Field(default=None, exclude=True)


class ConnectionState(BaseModel):
    status: Literal["not_tested", "ok", "ko"] = "not_tested"
    endpoint_tested: str | None = None
    latency_ms: float | None = None
    timestamp: datetime | None = None
    message: str = "No probado"
    error: str | None = None


class TestConnectionResponse(ConnectionState):
    details: dict[str, Any] = Field(default_factory=dict)


def _dashboard_parts(dashboard_url: str) -> dict[str, str | int]:
    if not dashboard_url:
        return {"dashboard_id": "", "team_id": "", "tab": 0}
    parsed = urlparse(dashboard_url)
    fragment = urlparse(parsed.fragment) if parsed.fragment else parsed
    parts = [part for part in fragment.path.split("/") if part]
    dashboard_id = parts[1] if len(parts) >= 2 and parts[0] == "dashboard" else ""
    params = parse_qs(fragment.query)
    tab = _first_int(params.get("tab"), 0)
    team_id = _first_text(params.get("teamID"), "")
    return {"dashboard_id": dashboard_id, "team_id": team_id, "tab": tab}


def public_quantum_config(config: QuantumConfig) -> QuantumPublicConfig:
    return QuantumPublicConfig(
        browser=config.browser,
        session_mode=config.session_mode,
        country=config.country,
        countries=[
            _public_country_config(item, item.country == config.country)
            for item in config.countries
        ],
        verify_tls=config.verify_tls,
        ingestion_depth_days=config.ingestion_depth_days,
        theme_preference=config.theme_preference,
        export_path=config.export_path,
    )


def _public_country_config(
    item: QuantumCountryConfig,
    is_default: bool,
) -> QuantumPublicCountryConfig:
    dashboard = item.default_dashboard()
    return QuantumPublicCountryConfig(
        country=item.country,
        base_url=item.base_url,
        timezone=item.timezone,
        enabled=item.enabled,
        is_default=is_default,
        dashboard_resolved=bool(dashboard and dashboard.validated),
        dashboards=item.dashboards,
    )


def merge_public_quantum_update(
    existing: QuantumConfig,
    update: QuantumPublicConfigUpdate,
) -> QuantumConfigUpdate:
    existing_by_country = {item.country: item for item in existing.countries}
    default_country = (
        update.country
        if any(item.country == update.country for item in update.countries)
        else (update.countries[0].country if update.countries else update.country)
    )
    countries: list[QuantumCountryConfig] = []
    for item in update.countries:
        previous = existing_by_country.get(item.country)
        dashboards = item.dashboards or (previous.dashboards if previous else [])
        countries.append(
            QuantumCountryConfig(
                country=item.country,
                base_url=item.base_url,
                timezone=item.timezone or COUNTRY_TIMEZONES[item.country],
                dashboard_id=(previous.dashboard_id if previous else ""),
                team_id=(previous.team_id if previous else ""),
                tab=(previous.tab if previous else 0),
                enabled=item.enabled,
                dashboards=_normalized_dashboards(dashboards),
            )
        )
    return QuantumConfigUpdate(
        schema_version=existing.schema_version,
        browser=update.browser,
        session_mode=update.session_mode,
        country=default_country,
        countries=countries,
        verify_tls=update.verify_tls,
        ingestion_depth_days=update.ingestion_depth_days,
        theme_preference=update.theme_preference,
        export_path=update.export_path,
        manual_cookie=update.manual_cookie,
    )


def _normalized_dashboards(
    dashboards: list[QuantumDashboardConfig],
) -> list[QuantumDashboardConfig]:
    if not dashboards:
        return []
    default_seen = False
    normalized: list[QuantumDashboardConfig] = []
    for dashboard in dashboards:
        is_default = dashboard.is_default and not default_seen
        if is_default:
            default_seen = True
        normalized.append(dashboard.model_copy(update={"is_default": is_default}))
    return normalized


def _tabs_from_widgets(widgets: list[QuantumWidgetConfig]) -> list[QuantumDashboardTabConfig]:
    seen: set[tuple[int, str]] = set()
    tabs: list[QuantumDashboardTabConfig] = []
    for widget in widgets:
        name = widget.tab_name or _tab_label(widget.tab)
        key = (widget.tab_index, name)
        if key in seen:
            continue
        seen.add(key)
        tabs.append(
            QuantumDashboardTabConfig(
                tab_index=widget.tab_index,
                name=name,
                normalized_role=widget.tab if widget.tab in {"summary", "errors"} else None,
            )
        )
    return sorted(tabs, key=lambda tab: (tab.tab_index, tab.name.casefold()))


def _tab_label(tab: str) -> str:
    if tab == "summary":
        return "Resumen"
    if tab == "errors":
        return "Errores"
    return tab or "Tab"


def _is_legacy_generated_dashboard_name(value: str, dashboard_id: str = "") -> bool:
    return bool(dashboard_id and value == dashboard_id) or value == " ".join(
        ("Dashboard", "default")
    )


def _first_text(values: list[str] | None, default: str) -> str:
    if not values:
        return default
    return values[0]


def _first_int(values: list[str] | None, default: int) -> int:
    if not values:
        return default
    try:
        return int(values[0])
    except ValueError:
        return default
