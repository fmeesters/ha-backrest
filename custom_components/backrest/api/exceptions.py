"""Exceptions raised by the Backrest API client."""

from __future__ import annotations


class BackrestError(Exception):
    """Base class for all Backrest API errors."""


class BackrestConnectionError(BackrestError):
    """Backrest could not be reached or did not answer in time."""


class BackrestAuthenticationError(BackrestError):
    """Backrest rejected the credentials."""


class BackrestResponseError(BackrestError):
    """Backrest answered with an error or an unexpected payload."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        """Store the Connect error code next to the message."""
        super().__init__(message)
        self.code = code
