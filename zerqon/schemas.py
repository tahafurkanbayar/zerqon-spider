"""Pydantic giriş/çıkış modelleri (API ve form doğrulaması)."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from zerqon import DEFAULT_USER_AGENT

RenderMode = Literal["standard", "javascript", "hybrid"]

MAX_PATTERN_LINES = 50
MAX_PATTERN_LENGTH = 300


def _validate_patterns(value: str) -> str:
    lines = [line.strip() for line in (value or "").splitlines() if line.strip()]
    if len(lines) > MAX_PATTERN_LINES:
        raise ValueError(f"En fazla {MAX_PATTERN_LINES} kural girilebilir")
    for line in lines:
        if len(line) > MAX_PATTERN_LENGTH:
            raise ValueError(f"Kural çok uzun (en fazla {MAX_PATTERN_LENGTH} karakter)")
        try:
            re.compile(line)
        except re.error as exc:
            raise ValueError(f"Geçersiz düzenli ifade: {line} ({exc})") from exc
    return "\n".join(lines)


class CrawlSettingsModel(BaseModel):
    """Bir projenin varsayılan veya bir taramanın anlık tarama ayarları."""

    model_config = ConfigDict(str_strip_whitespace=True)

    max_urls: int = Field(default=500, ge=1, le=500_000)
    max_depth: int = Field(default=10, ge=0, le=100)
    concurrency: int = Field(default=4, ge=1, le=50)
    delay_ms: int = Field(default=250, ge=0, le=60_000)
    timeout_seconds: float = Field(default=20, ge=1, le=120)
    max_retries: int = Field(default=2, ge=0, le=10)
    user_agent: str = Field(default=DEFAULT_USER_AGENT, min_length=3, max_length=400)
    include_subdomains: bool = False
    include_patterns: str = ""
    exclude_patterns: str = ""
    render_mode: RenderMode = "standard"
    max_render_pages: int = Field(default=200, ge=0, le=100_000)
    use_sitemaps: bool = True
    check_images: bool = True
    allow_localhost: bool = False

    title_min_chars: int = Field(default=30, ge=1, le=500)
    title_max_chars: int = Field(default=60, ge=1, le=500)
    description_min_chars: int = Field(default=70, ge=1, le=1000)
    description_max_chars: int = Field(default=160, ge=1, le=1000)
    min_word_count: int = Field(default=200, ge=0, le=100_000)
    max_url_length: int = Field(default=115, ge=10, le=10_000)
    large_image_bytes: int = Field(default=204_800, ge=1024, le=100 * 1024 * 1024)
    deep_page_depth: int = Field(default=4, ge=1, le=100)

    @field_validator("include_patterns", "exclude_patterns")
    @classmethod
    def _patterns(cls, value: str) -> str:
        return _validate_patterns(value)

    @field_validator("user_agent")
    @classmethod
    def _user_agent(cls, value: str) -> str:
        if any(ch in value for ch in "\r\n\x00"):
            raise ValueError("User-Agent kontrol karakteri içeremez")
        return value

    @model_validator(mode="after")
    def _ranges(self) -> CrawlSettingsModel:
        if self.title_min_chars > self.title_max_chars:
            raise ValueError("Title minimum uzunluğu maksimumdan büyük olamaz")
        if self.description_min_chars > self.description_max_chars:
            raise ValueError("Description minimum uzunluğu maksimumdan büyük olamaz")
        return self


SETTINGS_FIELDS: tuple[str, ...] = tuple(CrawlSettingsModel.model_fields)
BOOL_SETTINGS: frozenset[str] = frozenset(
    name for name, field in CrawlSettingsModel.model_fields.items() if field.annotation is bool
)


class ProjectCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    start_url: str = Field(min_length=4, max_length=2000)

    @field_validator("start_url")
    @classmethod
    def _start_url(cls, value: str) -> str:
        from zerqon.crawler.urls import InvalidURLError, validate_start_url

        try:
            return validate_start_url(value)
        except InvalidURLError as exc:
            raise ValueError(str(exc)) from exc


class CrawlStartRequest(BaseModel):
    permission_confirmed: bool

    @field_validator("permission_confirmed")
    @classmethod
    def _must_confirm(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Tarama için site sahipliği / tarama izni onayı zorunludur")
        return value
