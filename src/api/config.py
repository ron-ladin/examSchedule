from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application-wide configuration loaded from environment / .env file."""

    cors_origins: list[str] = ["http://localhost:5173"]
    server_port: int = 8000
    generation_timeout_seconds: int = 120

    class Config:
        env_file = ".env"


settings = Settings()
