from __future__ import annotations

# Tests for domain exception classes (SCRUM-65)
# Each test checks one specific behaviour of the four custom exception types.

import pytest

from src.api.exceptions.domain import (
    BusyError,
    ConflictError,
    DomainValidationError,
    NotFoundError,
)


# --- Sanity: each type can be raised and caught by its own type ---

def test_not_found_caught_by_own_type() -> None:
    # NotFoundError raised inside a try block is caught by NotFoundError
    with pytest.raises(NotFoundError):
        raise NotFoundError("thing not found")


def test_conflict_caught_by_own_type() -> None:
    # ConflictError raised inside a try block is caught by ConflictError
    with pytest.raises(ConflictError):
        raise ConflictError("already exists")


def test_domain_validation_caught_by_own_type() -> None:
    # DomainValidationError raised inside a try block is caught by DomainValidationError
    with pytest.raises(DomainValidationError):
        raise DomainValidationError("bad input")


def test_busy_caught_by_own_type() -> None:
    # BusyError raised inside a try block is caught by BusyError
    with pytest.raises(BusyError):
        raise BusyError("still running")


# --- Sanity: each can be caught by the base Exception type ---

def test_not_found_caught_by_base_exception() -> None:
    # NotFoundError is a subclass of Exception and can be caught generically
    with pytest.raises(Exception):
        raise NotFoundError("x")


def test_conflict_caught_by_base_exception() -> None:
    # ConflictError is a subclass of Exception and can be caught generically
    with pytest.raises(Exception):
        raise ConflictError("x")


def test_domain_validation_caught_by_base_exception() -> None:
    # DomainValidationError is a subclass of Exception and can be caught generically
    with pytest.raises(Exception):
        raise DomainValidationError("x")


def test_busy_caught_by_base_exception() -> None:
    # BusyError is a subclass of Exception and can be caught generically
    with pytest.raises(Exception):
        raise BusyError("x")


# --- Sanity: str(exc) returns the message passed to the constructor ---

def test_not_found_str_message() -> None:
    # str() of a NotFoundError equals the constructor argument
    exc = NotFoundError("course 42 not found")
    assert str(exc) == "course 42 not found"


def test_conflict_str_message() -> None:
    # str() of a ConflictError equals the constructor argument
    exc = ConflictError("already uploaded")
    assert str(exc) == "already uploaded"


def test_domain_validation_str_message() -> None:
    # str() of a DomainValidationError equals the constructor argument
    exc = DomainValidationError("bad program id")
    assert str(exc) == "bad program id"


def test_busy_str_message() -> None:
    # str() of a BusyError equals the constructor argument
    exc = BusyError("generation in progress")
    assert str(exc) == "generation in progress"


# --- Sanity: all 4 are direct subclasses of Exception ---

def test_not_found_direct_subclass_of_exception() -> None:
    # NotFoundError.__bases__ must include Exception directly
    assert Exception in NotFoundError.__bases__


def test_conflict_direct_subclass_of_exception() -> None:
    # ConflictError.__bases__ must include Exception directly
    assert Exception in ConflictError.__bases__


def test_domain_validation_direct_subclass_of_exception() -> None:
    # DomainValidationError.__bases__ must include Exception directly
    assert Exception in DomainValidationError.__bases__


def test_busy_direct_subclass_of_exception() -> None:
    # BusyError.__bases__ must include Exception directly
    assert Exception in BusyError.__bases__


# --- Boundary: empty string message ---

def test_not_found_empty_message() -> None:
    # An empty-string message should survive round-trip through str()
    exc = NotFoundError("")
    assert str(exc) == ""


def test_conflict_empty_message() -> None:
    # An empty-string message on ConflictError survives round-trip
    exc = ConflictError("")
    assert str(exc) == ""


def test_domain_validation_empty_message() -> None:
    # An empty-string message on DomainValidationError survives round-trip
    exc = DomainValidationError("")
    assert str(exc) == ""


def test_busy_empty_message() -> None:
    # An empty-string message on BusyError survives round-trip
    exc = BusyError("")
    assert str(exc) == ""


# --- Boundary: very long message (500 chars) is preserved exactly ---

def test_not_found_long_message_preserved() -> None:
    # A 500-character message must be stored and returned verbatim
    long_msg = "x" * 500
    exc = NotFoundError(long_msg)
    assert str(exc) == long_msg


# --- Boundary: message with special characters is preserved ---

def test_message_with_newline_preserved() -> None:
    # Newline inside message must survive str() unchanged
    exc = NotFoundError("line1\nline2")
    assert str(exc) == "line1\nline2"


def test_message_with_quotes_preserved() -> None:
    # Single and double quotes inside message must survive str() unchanged
    exc = ConflictError("it's a \"conflict\"")
    assert str(exc) == "it's a \"conflict\""


def test_message_with_unicode_preserved() -> None:
    # Unicode characters inside message must survive str() unchanged
    exc = DomainValidationError("מחלקה לא חוקית")
    assert str(exc) == "מחלקה לא חוקית"


# --- Negative: NotFoundError is NOT caught by ConflictError ---

def test_not_found_not_caught_by_conflict() -> None:
    # Catching ConflictError must NOT suppress a NotFoundError
    raised = False
    try:
        raise NotFoundError("missing")
    except ConflictError:
        pass
    except NotFoundError:
        raised = True
    assert raised


# --- Negative: NotFoundError is NOT caught by BusyError ---

def test_not_found_not_caught_by_busy() -> None:
    # Catching BusyError must NOT suppress a NotFoundError
    raised = False
    try:
        raise NotFoundError("missing")
    except BusyError:
        pass
    except NotFoundError:
        raised = True
    assert raised


# --- Edge: exception can be re-raised and still carries the original message ---

def test_reraise_preserves_message() -> None:
    # Re-raising an exception must not lose the original message
    original = NotFoundError("original message")
    try:
        try:
            raise original
        except NotFoundError:
            raise
    except NotFoundError as exc:
        assert str(exc) == "original message"


# --- Edge: all 4 types are distinct classes (none is a subclass of another) ---

def test_all_four_types_are_distinct() -> None:
    # No domain exception should be a subclass of another domain exception
    types = [NotFoundError, ConflictError, DomainValidationError, BusyError]
    for i, t1 in enumerate(types):
        for j, t2 in enumerate(types):
            if i != j:
                assert not issubclass(t1, t2), f"{t1.__name__} should not be a subclass of {t2.__name__}"
