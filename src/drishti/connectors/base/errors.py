from __future__ import annotations


class ConnectorError(Exception):
    """Base class for connector failures."""


class AuthError(ConnectorError):
    """The source rejected the connector credentials."""


class RateLimitError(ConnectorError):
    """The source throttled the request."""

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class TransientError(ConnectorError):
    """A retryable transport or 5xx source failure."""


class PermanentError(ConnectorError):
    """A non-retryable source failure."""


class UnsupportedResource(ConnectorError):
    """The connector does not implement the requested resource."""
