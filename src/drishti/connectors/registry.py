from __future__ import annotations

from pathlib import Path
from typing import Any

from drishti.config import Settings
from drishti.connectors.base import (
    Connector,
    ConnectorConnection,
    LiveTransport,
    MockTransport,
    NoopRateLimiter,
    RedisRateLimiter,
    Transport,
    UnsupportedResource,
)
from drishti.connectors.shopify import ShopifyConnector


CONNECTOR_REGISTRY = {
    "shopify": ShopifyConnector,
}


def build_connector(
    connection: ConnectorConnection,
    *,
    settings: Settings,
    redis: Any | None = None,
    fixture_root: str | Path = "fixtures",
) -> Connector:
    connector_class = CONNECTOR_REGISTRY.get(connection.source)
    if connector_class is None:
        raise UnsupportedResource(f"Unsupported connector source {connection.source!r}")

    transport = build_transport(connection.source, settings=settings, fixture_root=fixture_root)
    rate_limiter = (
        RedisRateLimiter(redis)
        if redis is not None and settings.transport_mode == "live"
        else NoopRateLimiter()
    )
    return connector_class(connection, transport, rate_limiter)


def build_transport(
    source: str,
    *,
    settings: Settings,
    fixture_root: str | Path = "fixtures",
) -> Transport:
    if settings.transport_mode == "live":
        return LiveTransport()
    return MockTransport(Path(fixture_root) / source)
