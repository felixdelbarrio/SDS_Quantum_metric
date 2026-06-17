from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from pydantic import BaseModel, Field, field_validator, model_validator


class BrowserName(StrEnum):
    chrome = "chrome"
    edge = "edge"
    safari = "safari"
    firefox = "firefox"


class SessionMode(StrEnum):
    browser = "browser"
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


class QuantumCountryConfig(BaseModel):
    country: Country
    base_url: str = ""
    dashboard_id: str = ""
    team_id: str = ""
    tab: int = Field(default=0, ge=0)
    enabled: bool = True

    @field_validator("base_url", "dashboard_id", "team_id", mode="before")
    @classmethod
    def _strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    def is_ready_for_ingestion(self) -> bool:
        return bool(self.enabled and self.base_url and self.dashboard_id)

    def dashboard_url(self) -> str:
        if not self.base_url or not self.dashboard_id:
            raise ValueError("Country config needs base_url and dashboard_id.")
        fragment_path = f"/dashboard/{self.dashboard_id}"
        query = urlencode(
            {
                "tab": self.tab,
                **({"teamID": self.team_id} if self.team_id else {}),
            }
        )
        fragment = f"{fragment_path}?{query}" if query else fragment_path
        parsed = urlparse(self.base_url)
        base = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
        return f"{base.rstrip()}/#{fragment}"


class QuantumConfig(BaseModel):
    browser: BrowserName = BrowserName.chrome
    session_mode: SessionMode = SessionMode.browser
    country: Country = Country.MX
    countries: list[QuantumCountryConfig] = Field(default_factory=list)
    verify_tls: bool = True
    ingestion_depth_days: int = Field(default=30, ge=1, le=3650)
    theme_preference: Literal["system", "light", "dark"] = "system"

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_single_country(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        if value.get("countries"):
            return value

        country = value.get("country") or Country.MX.value
        dashboard_parts = _dashboard_parts(str(value.get("dashboard_url") or ""))
        legacy = QuantumCountryConfig(
            country=Country(country),
            base_url=str(value.get("base_url") or "https://bbvamx.quantummetric.com"),
            dashboard_id=str(dashboard_parts["dashboard_id"]),
            team_id=str(dashboard_parts["team_id"]),
            tab=int(dashboard_parts["tab"]),
        )
        migrated = dict(value)
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
                    dashboard_id="8e53eb82-587c-4b92-a0fa-0f6283677e28",
                    team_id="1da677de-9313-4b49-9110-81a6b756ca7e",
                    tab=0,
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
    enabled: bool = True
    dashboard_resolved: bool = False


class QuantumPublicConfig(BaseModel):
    browser: BrowserName = BrowserName.chrome
    session_mode: SessionMode = SessionMode.browser
    country: Country = Country.MX
    countries: list[QuantumPublicCountryConfig] = Field(default_factory=list)
    verify_tls: bool = True
    ingestion_depth_days: int = Field(default=30, ge=1, le=3650)
    theme_preference: Literal["system", "light", "dark"] = "system"


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
            QuantumPublicCountryConfig(
                country=item.country,
                base_url=item.base_url,
                enabled=item.enabled,
                dashboard_resolved=bool(item.dashboard_id),
            )
            for item in config.countries
        ],
        verify_tls=config.verify_tls,
        ingestion_depth_days=config.ingestion_depth_days,
        theme_preference=config.theme_preference,
    )


def merge_public_quantum_update(
    existing: QuantumConfig,
    update: QuantumPublicConfigUpdate,
) -> QuantumConfigUpdate:
    existing_by_country = {item.country: item for item in existing.countries}
    countries: list[QuantumCountryConfig] = []
    for item in update.countries:
        previous = existing_by_country.get(item.country)
        countries.append(
            QuantumCountryConfig(
                country=item.country,
                base_url=item.base_url,
                dashboard_id=previous.dashboard_id if previous else "",
                team_id=previous.team_id if previous else "",
                tab=previous.tab if previous else 0,
                enabled=item.enabled,
            )
        )
    return QuantumConfigUpdate(
        browser=update.browser,
        session_mode=update.session_mode,
        country=update.country,
        countries=countries,
        verify_tls=update.verify_tls,
        ingestion_depth_days=update.ingestion_depth_days,
        theme_preference=update.theme_preference,
        manual_cookie=update.manual_cookie,
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
