"""Runtime configuration."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FINAGENTIC_", env_file=".env")

    #: The SEC blocks clients that do not identify themselves, and asks that the
    #: value name a real contact. See https://www.sec.gov/os/webmaster-faq#developers
    sec_user_agent: str = "fin-agentic (contact: levirankin1@gmail.com)"

    #: Where raw EDGAR payloads are cached. Keeping them means a tag-map fix can
    #: be re-applied to every company without re-fetching several MB each.
    cache_dir: Path = Path(".edgar_cache")

    #: How many annual periods a statement shows by default.
    default_periods: int = 5

    cors_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
