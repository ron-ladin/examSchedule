from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response body for the health-check endpoint."""

    status: str


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Return a simple OK signal so load-balancers and CI know the server is up."""
    return HealthResponse(status="ok")
