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
            session_mode=SessionMode(self.settings.qm_session_mode),
            country=Country(self.settings.qm_country),
            countries=self._countries_from_settings(),
            verify_tls=self.settings.qm_verify_tls,
            ingestion_depth_days=self.settings.quantum_ingestion_depth_days,
            theme_preference=theme_preference,
        )

    def read(self) -> QuantumConfig:
        path = self.path if self.path.exists() else self.legacy_path
        if not path.exists():
            return self.default()
        data = json.loads(path.read_text())
        config = QuantumConfig.model_validate(data)
        if path == self.legacy_path and not self.path.exists():
            self._write_json(config)
        return config

    def write(self, update: QuantumConfigUpdate) -> QuantumConfig:
        config = QuantumConfig.model_validate(update.model_dump(exclude={"manual_cookie"}))
        self._write_json(config)
        self._sync_env(config)
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

    def _sync_env(self, config: QuantumConfig) -> None:
        if not self._should_sync_env():
            return

        selected = config.country_config() or config.countries[0]
        dashboard = selected.default_dashboard()
        values = {
            "QM_BASE_URL": selected.base_url,
            "QM_BROWSER": config.browser.value,
            "QM_SESSION_MODE": config.session_mode.value,
            "QM_COUNTRY": config.country.value,
            "QM_VERIFY_TLS": "true" if config.verify_tls else "false",
            "QUANTUM_INGESTION_DEPTH_DAYS": str(config.ingestion_depth_days),
            "QUANTUM_THEME_PREFERENCE": config.theme_preference,
            "QM_DASHBOARD_ID": dashboard.dashboard_id if dashboard else selected.dashboard_id,
            "QM_TEAM_ID": dashboard.team_id if dashboard else selected.team_id,
            "QM_DASHBOARD_TAB": str(dashboard.summary_tab if dashboard else selected.tab),
            "QM_COUNTRY_CONFIGS": json.dumps(
                [country.model_dump(mode="json") for country in config.countries],
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        }

        env_path = Path(".env")
        lines = env_path.read_text().splitlines() if env_path.exists() else []
        next_lines: list[str] = []
        written: set[str] = set()
        for line in lines:
            key = line.split("=", 1)[0].strip() if "=" in line else ""
            if key == "QM_DEFAULT_DASHBOARD_URL":
                continue
            if key in values:
                next_lines.append(f"{key}={values[key]}")
                written.add(key)
                continue
            next_lines.append(line)

        for key, value in values.items():
            if key not in written:
                next_lines.append(f"{key}={value}")

        env_path.write_text("\n".join(next_lines).rstrip() + "\n")

    def _should_sync_env(self) -> bool:
        try:
            self.settings.qm_data_dir.resolve().relative_to(Path.cwd().resolve())
        except ValueError:
            return False
        return True


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
