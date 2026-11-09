from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ei_db.session import DEFAULT_URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(default=DEFAULT_URL, alias="DATABASE_URL")
    api_cors_origins: str = Field(default="http://localhost:3000", alias="API_CORS_ORIGINS")
    #: Optional regex for extra origins, e.g. Vercel preview deployments:
    #: ^https://epidemic-intelligence-[a-z0-9-]+\.vercel\.app$
    api_cors_origin_regex: str | None = Field(default=None, alias="API_CORS_ORIGIN_REGEX")
    #: Seconds browsers/CDNs may cache successful GETs; 0 disables caching.
    cache_max_age: int = Field(default=300, alias="API_CACHE_MAX_AGE")
    version: str = "0.1.0"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
