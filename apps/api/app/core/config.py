from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="JSTYLE_", extra="ignore")

    env: str = "local"
    database_url: str = "postgresql+psycopg://jstyle:jstyle@localhost:5432/jstyle"
    redis_url: str = "redis://localhost:6379/0"
    public_base_url: str = "http://localhost:3000"

    # Sign-in: exactly one Google account may use the CRM.
    allowed_email: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    # Signs the short-lived OAuth state cookie. Generate with `openssl rand -hex 32`.
    secret_key: str = "dev-only-change-me"

    session_idle_hours: int = 12
    session_absolute_days: int = 30

    @property
    def secure_cookies(self) -> bool:
        return self.public_base_url.startswith("https://")


@lru_cache
def get_settings() -> Settings:
    return Settings()
