from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.app.config.paths import default_user_data_dir, default_user_log_dir


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    qm_base_url: str = "https://bbvamx.quantummetric.com"
    qm_browser: str = "chrome"
    qm_session_mode: str = "browser"
    qm_country: str = "MX"
    qm_verify_tls: bool = True
    qm_data_dir: Path = Field(default_factory=default_user_data_dir)
    logs_dir: Path = Field(default_factory=default_user_log_dir)
    qm_dashboard_id: str = ""
    qm_team_id: str = ""
    qm_dashboard_tab: int = 0
    qm_country_configs: str = ""
    quantum_default_base_url: str = "https://bbvamx.quantummetric.com"
    quantum_default_dashboard_id: str = "8e53eb82-587c-4b92-a0fa-0f6283677e28"
    quantum_default_team_id: str = "1da677de-9313-4b49-9110-81a6b756ca7e"
    quantum_default_summary_tab: int = 0
    quantum_default_errors_tab: int = 1
    quantum_capture_timeout_seconds: int = 120
    quantum_regression_tolerance_percent: float = 0.1
    quantum_ingestion_depth_days: int = 365
    quantum_incremental_reprocess_days: int = 1
    quantum_ingestion_chunk_days: int = 1
    quantum_theme_preference: str = "system"
    qm_default_dashboard_url: str = (
        "https://bbvamx.quantummetric.com/#/dashboard/"
        "8e53eb82-587c-4b92-a0fa-0f6283677e28"
        "?tab=0&teamID=1da677de-9313-4b49-9110-81a6b756ca7e"
    )
    backend_host: str = "127.0.0.1"
    backend_port: int = 8765
    frontend_host: str = "127.0.0.1"
    frontend_port: int = 5173
    chrome_cookie_profile: str = "Default"
    chrome_executable: Path = Field(
        default=Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    )

    @property
    def config_dir(self) -> Path:
        return self.qm_data_dir / "config"

    @property
    def parquet_dir(self) -> Path:
        return self.qm_data_dir / "parquet"

    @property
    def manifests_dir(self) -> Path:
        return self.qm_data_dir / "manifests"

    @property
    def exports_dir(self) -> Path:
        return self.qm_data_dir / "exports"

    @property
    def runtime_dir(self) -> Path:
        return self.qm_data_dir / "runtime"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    for directory in [
        settings.config_dir,
        settings.parquet_dir,
        settings.manifests_dir,
        settings.exports_dir,
        settings.runtime_dir,
        settings.logs_dir,
    ]:
        directory.mkdir(parents=True, exist_ok=True)
    return settings
