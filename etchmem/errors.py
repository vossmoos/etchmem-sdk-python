"""Exception hierarchy for the etchmem SDK."""
from __future__ import annotations

from typing import Any


class EtchMemError(Exception):
    """Base class for all etchmem SDK errors."""


class ConnectionError(EtchMemError):
    """The server could not be reached (network error, timeout, DNS)."""


class APIError(EtchMemError):
    """The server returned a non-2xx HTTP status."""

    def __init__(self, status_code: int, detail: Any = None) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


class NotFoundError(APIError):
    """404 — resource (e.g. etch id) does not exist."""


class AuthenticationError(APIError):
    """401 / 403 — missing or invalid API key."""


class ServerError(APIError):
    """5xx — the server failed to process the request."""


def error_for_status(status_code: int, detail: Any) -> APIError:
    """Map an HTTP status code to the most specific APIError subclass."""
    if status_code == 404:
        return NotFoundError(status_code, detail)
    if status_code in (401, 403):
        return AuthenticationError(status_code, detail)
    if status_code >= 500:
        return ServerError(status_code, detail)
    return APIError(status_code, detail)
