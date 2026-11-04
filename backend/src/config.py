from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.paths import default_database_url


class Settings(BaseSettings):
    # DATABASE_URL in the environment or .env overrides the per-user data directory.
    database_url: str = Field(default_factory=default_database_url)
    s2_api_key: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
