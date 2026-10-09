"""Uygulama yapılandırması (.env + ortam değişkenleri)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ZERQON_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)
    data_dir: Path | None = None
    default_language: Literal["tr", "en"] = "tr"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    allow_localhost: bool = False

    max_concurrency: int = Field(default=20, ge=1, le=100)
    max_urls_hard_limit: int = Field(default=500_000, ge=1)
    max_body_bytes: int = Field(default=5 * 1024 * 1024, ge=64 * 1024)
    render_timeout_seconds: int = Field(default=20, ge=3, le=120)
    max_render_contexts: int = Field(default=3, ge=1, le=10)

    @field_validator("data_dir", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if value in ("", None):
            return None
        return value

    @property
    def resolved_data_dir(self) -> Path:
        return (self.data_dir or PROJECT_ROOT / "data").resolve()

    @property
    def db_path(self) -> Path:
        return self.resolved_data_dir / "zerqon.db"

    @property
    def logs_dir(self) -> Path:
        return self.resolved_data_dir / "logs"

    @property
    def reports_dir(self) -> Path:
        return self.resolved_data_dir / "reports"

    @property
    def backups_dir(self) -> Path:
        return self.resolved_data_dir / "backups"

    def ensure_dirs(self) -> None:
        for path in (self.resolved_data_dir, self.logs_dir, self.reports_dir, self.backups_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
