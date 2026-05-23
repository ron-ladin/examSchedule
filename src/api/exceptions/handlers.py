from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from src.api.exceptions.domain import (
    BusyError,
    ConflictError,
    DomainValidationError,
    NotFoundError,
)
from src.api.schemas.error import ErrorDTO

logger = logging.getLogger(__name__)

# Type alias: the signature FastAPI/Starlette expects for exception handlers
ExceptionHandler = Callable[[Request, Exception], Awaitable[Response]]


def _domain_handler(status_code: int, code: str) -> ExceptionHandler:
    """Build a handler that converts a domain exception to a JSON error response.

    Why a factory instead of 4 separate functions:
    All domain exceptions follow the same pattern — str(exc) becomes the detail,
    only the status code and error code string differ. One factory eliminates the
    repetition without sacrificing readability at the registration site.

    The closure captures status_code and code by value via function arguments,
    so each returned handler is completely independent (no shared-mutable-state bug).
    """
    async def handler(request: Request, exc: Exception) -> Response:
        return JSONResponse(
            status_code=status_code,
            content=ErrorDTO(detail=str(exc), code=code).model_dump(),
        )
    return handler  # type: ignore[return-value]


async def _unhandled_handler(request: Request, exc: Exception) -> Response:
    """Catch-all for any exception not matched by a specific handler.

    Always logs the full traceback (so nothing is silently swallowed) and returns
    a generic 500 body — never exposing internal details or stack traces to clients.

    Note: FastAPI pre-registers handlers for HTTPException and RequestValidationError.
    Starlette's MRO-based lookup finds those specific handlers first, so this handler
    is only reached by truly unhandled exceptions (bugs, unexpected states, etc.).
    """
    logger.exception(
        "Unhandled exception on %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content=ErrorDTO(detail="Internal server error", code="INTERNAL_ERROR").model_dump(),
    )


def register_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the app. Call once inside create_app().

    Never use @app.exception_handler decorator outside this function — all handler
    registration must go through here so it is easy to audit what is handled.
    """
    app.add_exception_handler(NotFoundError, _domain_handler(404, "NOT_FOUND"))  # type: ignore[arg-type]
    app.add_exception_handler(ConflictError, _domain_handler(409, "CONFLICT"))  # type: ignore[arg-type]
    app.add_exception_handler(DomainValidationError, _domain_handler(400, "VALIDATION_ERROR"))  # type: ignore[arg-type]
    app.add_exception_handler(BusyError, _domain_handler(409, "BUSY"))  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_handler)  # type: ignore[arg-type]
