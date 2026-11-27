from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="JSTYLE_", extra="ignore")

    env: str = "local"
    database_url: str = "postgresql+psycopg://jstyle:jstyle@localhost:5432/jstyle"
    redis_url: str = "redis://localhost:6379/0"
    allowed_email: str = ""
    public_base_url: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
