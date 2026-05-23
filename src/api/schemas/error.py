from __future__ import annotations

from pydantic import BaseModel


class ErrorDTO(BaseModel):
    """Shape of every error response body returned by the API."""

    detail: str
    code: str | None = None
