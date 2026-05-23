from __future__ import annotations

import os
from dataclasses import dataclass, field


def _parse_cors_origins(value: str | None) -> list[str]:
    """
    Parse CORS origins from an environment variable.

    Expected format:
        CORS_ORIGINS=http://localhost:5173,http://localhost:3000

    If not provided, use the default local frontend origin.
    """
    if not value:
        return ["http://localhost:5173"]

    return [origin.strip() for origin in value.split(",") if origin.strip()]


def _get_int_env(name: str, default: int) -> int:
    """
    Read an integer environment variable safely.
    If the value is missing or invalid, return the default.
    """
    value = os.getenv(name)

    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        return default


@dataclass
class Settings:
    """Application-wide configuration loaded from environment variables."""

    cors_origins: list[str] = field(
        default_factory=lambda: _parse_cors_origins(os.getenv("CORS_ORIGINS"))
    )
    server_port: int = field(
        default_factory=lambda: _get_int_env("SERVER_PORT", 8000)
    )
    generation_timeout_seconds: int = field(
        default_factory=lambda: _get_int_env("GENERATION_TIMEOUT_SECONDS", 120)
    )


settings = Settings()