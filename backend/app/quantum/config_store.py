from __future__ import annotations

import json
from pathlib import Path

from backend.app.config.settings import Settings
from backend.app.quantum.schemas import (
    BrowserName,
    Country,
    QuantumConfig,
    QuantumConfigUpdate,
    SessionMode,
)


class QuantumConfigStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = settings.config_dir / "quantum.json"

    def default(self) -> QuantumConfig:
        return QuantumConfig(
            browser=BrowserName(self.settings.qm_browser),
            base_url=self.settings.qm_base_url,
            session_mode=SessionMode(self.settings.qm_session_mode),
            country=Country(self.settings.qm_country),
            dashboard_url=self.settings.qm_default_dashboard_url,
            verify_tls=self.settings.qm_verify_tls,
        )

    def read(self) -> QuantumConfig:
        if not self.path.exists():
            return self.default()
        data = json.loads(self.path.read_text())
        return QuantumConfig.model_validate(data)

    def write(self, update: QuantumConfigUpdate) -> QuantumConfig:
        config = QuantumConfig.model_validate(update.model_dump(exclude={"manual_cookie"}))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(config.model_dump_json(indent=2))
        return config

    def delete(self) -> None:
        if self.path.exists():
            self.path.unlink()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
