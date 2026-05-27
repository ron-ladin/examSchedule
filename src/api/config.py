from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide configuration loaded from environment / .env file."""

    cors_origins: list[str] = ["http://localhost:5173"]
    server_port: int = 8000
    generation_timeout_seconds: int = 120
    # Set USE_PROCESS_POOL=false to use ThreadPoolExecutor instead (e.g. in tests).
    use_process_pool: bool = True

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
