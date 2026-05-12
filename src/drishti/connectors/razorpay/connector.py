from __future__ import annotations

import base64
from typing import ClassVar

from drishti.connectors.base import (
    Connector,
    ConnectorConnection,
    RateLimitConfig,
    RateLimiter,
    Transport,
    UnsupportedResource,
)


class RazorpayConnector(Connector):
    source: ClassVar[str] = "razorpay"
    base_url: ClassVar[str] = "https://api.razorpay.com"
    rate_limit_config: ClassVar[RateLimitConfig] = RateLimitConfig(
        requests_per_second=1,
        burst=10,
    )

    def __init__(
        self,
        connection: ConnectorConnection,
        transport: Transport,
        rate_limiter: RateLimiter,
    ) -> None:
        super().__init__(connection, transport, rate_limiter)

    async def authenticate(self) -> dict[str, str]:
        key_id = self.connection.auth_payload.get("key_id")
        key_secret = self.connection.auth_payload.get("key_secret")
        if not key_id or not key_secret:
            raise ValueError("Razorpay auth_payload.key_id and key_secret are required")
        token = base64.b64encode(f"{key_id}:{key_secret}".encode("utf-8")).decode("ascii")
        return {
            "authorization": f"Basic {token}",
            "accept": "application/json",
            "content-type": "application/json",
        }

    async def refresh_credentials_if_needed(self) -> None:
        return None

    def syncer(self, resource: str):
        if resource == "payments":
            from drishti.connectors.razorpay.syncers.payments import RazorpayPaymentsSyncer

            return RazorpayPaymentsSyncer(self)
        if resource == "refunds":
            from drishti.connectors.razorpay.syncers.refunds import RazorpayRefundsSyncer

            return RazorpayRefundsSyncer(self)
        if resource == "settlements":
            from drishti.connectors.razorpay.syncers.settlements import RazorpaySettlementsSyncer

            return RazorpaySettlementsSyncer(self)
        raise UnsupportedResource(f"Razorpay does not support resource {resource!r}")
