from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Sprawdzeni Fachowcy API"
    environment: str = "development"
    database_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
