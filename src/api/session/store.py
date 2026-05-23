from __future__ import annotations

from fastapi import Request

from src.api.session.models import SessionData


class SessionStore:
    """Owns the single shared SessionData for v1.0 (no auth).

    Why a class instead of a module-level variable:
    The lifespan creates one SessionStore per app startup and attaches it to
    app.state. Tests can call create_app() and get a fresh, isolated store
    each time — no cross-test state leakage.
    """

    def __init__(self) -> None:
        self._session: SessionData = SessionData()

    def get_or_create(self) -> SessionData:
        """Return the single session. Always exists after __init__."""
        return self._session

    def reset(self) -> None:
        """Replace the session with a blank one, discarding all previous state."""
        self._session = SessionData()


def get_session(request: Request) -> SessionData:
    """FastAPI dependency — inject the current session into a route handler.

    Usage:
        @router.get("/foo")
        def my_route(session: SessionData = Depends(get_session)) -> ...:
    """
    store: SessionStore = request.app.state.session_store
    return store.get_or_create()
