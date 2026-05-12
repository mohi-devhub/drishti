"""Shared connector primitives."""

from drishti.connectors.base.connector import Connector, ConnectorConnection
from drishti.connectors.base.errors import (
    AuthError,
    ConnectorError,
    PermanentError,
    RateLimitError,
    TransientError,
    UnsupportedResource,
)
from drishti.connectors.base.rate_limiter import NoopRateLimiter, RateLimitConfig, RedisRateLimiter
from drishti.connectors.base.resource_syncer import Page, ResourceSyncer
from drishti.connectors.base.transport import (
    LiveTransport,
    MockTransport,
    RecordingTransport,
    Transport,
    TransportResponse,
)

__all__ = [
    "AuthError",
    "Connector",
    "ConnectorConnection",
    "ConnectorError",
    "LiveTransport",
    "MockTransport",
    "NoopRateLimiter",
    "Page",
    "PermanentError",
    "RateLimitConfig",
    "RateLimitError",
    "RecordingTransport",
    "RedisRateLimiter",
    "ResourceSyncer",
    "TransientError",
    "Transport",
    "TransportResponse",
    "UnsupportedResource",
]

