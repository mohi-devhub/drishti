from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import ClassVar

from drishti.connectors.base import (
    Connector,
    ConnectorConnection,
    RateLimitConfig,
    RateLimiter,
    Transport,
    UnsupportedResource,
)


class ShiprocketConnector(Connector):
    source: ClassVar[str] = "shiprocket"
    base_url: ClassVar[str] = "https://apiv2.shiprocket.in"
    rate_limit_config: ClassVar[RateLimitConfig] = RateLimitConfig(
        requests_per_second=50 / 60,
        burst=5,
    )

    def __init__(
        self,
        connection: ConnectorConnection,
        transport: Transport,
        rate_limiter: RateLimiter,
    ) -> None:
        super().__init__(connection, transport, rate_limiter)

    async def authenticate(self) -> dict[str, str]:
        token = self.connection.auth_payload.get("token")
        if not token:
            raise ValueError("Shiprocket connection auth_payload.token is required")
        return {
            "authorization": f"Bearer {token}",
            "accept": "application/json",
            "content-type": "application/json",
        }

    async def refresh_credentials_if_needed(self) -> None:
        expires_at = self.connection.auth_payload.get("expires_at")
        if not expires_at:
            return None
        parsed = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        if parsed - datetime.now(UTC) < timedelta(hours=24):
            # Persisting refreshed secrets belongs in the connection service. The connector keeps
            # this as a visible boundary so fixture and live auth share the same request path.
            return None
        return None

    def syncer(self, resource: str):
        if resource == "shipments":
            from drishti.connectors.shiprocket.syncers.shipments import ShiprocketShipmentsSyncer

            return ShiprocketShipmentsSyncer(self)
        if resource == "tracking":
            from drishti.connectors.shiprocket.syncers.tracking import ShiprocketTrackingSyncer

            return ShiprocketTrackingSyncer(self)
        raise UnsupportedResource(f"Shiprocket does not support resource {resource!r}")
