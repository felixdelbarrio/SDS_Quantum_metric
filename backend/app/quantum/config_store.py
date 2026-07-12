from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal, cast

from backend.app.config.settings import Settings
from backend.app.quantum.schemas import (
    BrowserName,
    Country,
    QuantumConfig,
    QuantumConfigUpdate,
    QuantumCountryConfig,
    SessionMode,
    _dashboard_parts,
)


class QuantumConfigStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = settings.config_dir / "quantum_config.json"
        self.legacy_path = settings.config_dir / "quantum.json"

    def default(self) -> QuantumConfig:
        raw_theme = self.settings.quantum_theme_preference
        theme_preference: Literal["system", "light", "dark"] = (
            cast(Literal["system", "light", "dark"], raw_theme)
            if raw_theme in {"system", "light", "dark"}
            else "system"
        )
        return QuantumConfig(
            browser=BrowserName(self.settings.qm_browser),
            session_mode=SessionMode(_safe_default_session_mode(self.settings.qm_session_mode)),
            country=Country(self.settings.qm_country),
            countries=self._countries_from_settings(),
            verify_tls=self.settings.qm_verify_tls,
            ingestion_depth_days=self.settings.quantum_ingestion_depth_days,
            theme_preference=theme_preference,
            export_path=str(self.settings.qm_export_dir),
        )

    def read(self) -> QuantumConfig:
        path = self.path if self.path.exists() else self.legacy_path
        if not path.exists():
            return self.default()
        data = json.loads(path.read_text())
        config = _harden_browser_session_mode(QuantumConfig.model_validate(data))
        if path == self.legacy_path and not self.path.exists():
            self._write_json(config)
        elif data.get("session_mode") == SessionMode.browser.value:
            self._write_json(config)
        return config

    def write(self, update: QuantumConfigUpdate) -> QuantumConfig:
        config = _harden_browser_session_mode(
            QuantumConfig.model_validate(update.model_dump(exclude={"manual_cookie"}))
        )
        self._write_json(config)
        return config

    def delete(self) -> None:
        if self.path.exists():
            self.path.unlink()
        if self.legacy_path.exists():
            self.legacy_path.unlink()

    def _write_json(self, config: QuantumConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = config.model_dump_json(indent=2)
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            handle.write("\n")
            temporary = Path(handle.name)
        temporary.replace(self.path)

    def _countries_from_settings(self) -> list[QuantumCountryConfig]:
        if self.settings.qm_country_configs:
            try:
                raw_configs = json.loads(self.settings.qm_country_configs)
                if isinstance(raw_configs, list):
                    return [
                        QuantumCountryConfig.model_validate(item)
                        for item in raw_configs
                        if isinstance(item, dict)
                    ]
            except (TypeError, ValueError):
                pass

        dashboard_parts: dict[str, str | int] = {
            "dashboard_id": self.settings.qm_dashboard_id
            or self.settings.quantum_default_dashboard_id,
            "team_id": self.settings.qm_team_id or self.settings.quantum_default_team_id,
            "tab": self.settings.qm_dashboard_tab
            if self.settings.qm_dashboard_tab
            else self.settings.quantum_default_summary_tab,
        }
        if not dashboard_parts["dashboard_id"] and self.settings.qm_default_dashboard_url:
            dashboard_parts = _dashboard_parts(self.settings.qm_default_dashboard_url)

        return [
            QuantumCountryConfig(
                country=Country(self.settings.qm_country),
                base_url=self.settings.qm_base_url or self.settings.quantum_default_base_url,
                dashboard_id=str(dashboard_parts["dashboard_id"]),
                team_id=str(dashboard_parts["team_id"]),
                tab=int(dashboard_parts["tab"]),
            )
        ]


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _safe_default_session_mode(value: str) -> str:
    return "controlled" if value == "browser" else value


def _harden_browser_session_mode(config: QuantumConfig) -> QuantumConfig:
    if config.session_mode == SessionMode.browser:
        return config.model_copy(update={"session_mode": SessionMode.controlled})
    return config
