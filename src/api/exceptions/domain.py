from __future__ import annotations


class NotFoundError(Exception):
    """Raised when a requested resource does not exist.

    HTTP mapping: 404 Not Found.
    Example: course ID not in the session, period key missing.
    """


class ConflictError(Exception):
    """Raised when an operation would violate a uniqueness or state constraint.

    HTTP mapping: 409 Conflict.
    Example: uploading courses when courses are already loaded (replace mode off).
    """


class DomainValidationError(Exception):
    """Raised when input data breaks a domain business rule.

    HTTP mapping: 400 Bad Request.
    Example: program ID is not a valid 5-digit code, date range is empty.
    """


class BusyError(Exception):
    """Raised when the server is already running a background job.

    HTTP mapping: 409 Conflict.
    Example: POST /generate called while a generation job is already running.
    """
