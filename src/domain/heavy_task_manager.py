"""Single-owner throttle for expensive UI-triggered work.

The manager intentionally has no PyQt dependency. UI/controller code can use it
to prevent generation, loading, and ranking from competing for CPU, disk, and
SQLite resources at the same time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4


@dataclass(frozen=True)
class HeavyTaskToken:
    """Opaque ownership token for one active heavy task."""

    kind: str
    _owner_id: str = field(default_factory=lambda: uuid4().hex, repr=False)


class HeavyTaskManager:
    """Allow exactly one active heavy task and release it by owner token only."""

    def __init__(self) -> None:
        self._active: HeavyTaskToken | None = None

    @property
    def active_kind(self) -> str | None:
        """Return the active task kind, if any."""
        return self._active.kind if self._active is not None else None

    def is_active(self) -> bool:
        """Return True while a heavy task owns the slot."""
        return self._active is not None

    def begin(self, kind: str) -> HeavyTaskToken | None:
        """Reserve the heavy-task slot and return its owner token."""
        if self._active is not None:
            return None

        token = HeavyTaskToken(kind=kind)
        self._active = token
        return token

    def end(self, token: HeavyTaskToken) -> bool:
        """Release the slot only when *token* is the active owner."""
        if self._active != token:
            return False

        self._active = None
        return True
