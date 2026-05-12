from __future__ import annotations

from typing import ClassVar

from drishti.connectors.base import (
    Connector,
    ConnectorConnection,
    RateLimitConfig,
    RateLimiter,
    Transport,
    UnsupportedResource,
)

SHOPIFY_API_VERSION = "2026-01"


class ShopifyConnector(Connector):
    source: ClassVar[str] = "shopify"
    rate_limit_config: ClassVar[RateLimitConfig] = RateLimitConfig(
        requests_per_second=1.5,
        burst=10,
    )

    def __init__(
        self,
        connection: ConnectorConnection,
        transport: Transport,
        rate_limiter: RateLimiter,
    ) -> None:
        super().__init__(connection, transport, rate_limiter)
        shop = connection.auth_payload.get("shop")
        if not shop:
            raise ValueError("Shopify connection auth_payload.shop is required")
        self.shop = str(shop).replace("https://", "").replace("http://", "").strip("/")

    @property
    def base_url(self) -> str:
        return f"https://{self.shop}"

    async def authenticate(self) -> dict[str, str]:
        token = self.connection.auth_payload.get("access_token")
        if not token:
            raise ValueError("Shopify connection auth_payload.access_token is required")
        return {
            "x-shopify-access-token": str(token),
            "accept": "application/json",
            "content-type": "application/json",
        }

    async def refresh_credentials_if_needed(self) -> None:
        return None

    def syncer(self, resource: str):
        if resource == "orders":
            from drishti.connectors.shopify.syncers.orders import ShopifyOrdersSyncer

            return ShopifyOrdersSyncer(self)
        if resource == "customers":
            from drishti.connectors.shopify.syncers.customers import ShopifyCustomersSyncer

            return ShopifyCustomersSyncer(self)
        if resource == "products":
            from drishti.connectors.shopify.syncers.products import ShopifyProductsSyncer

            return ShopifyProductsSyncer(self)
        raise UnsupportedResource(f"Shopify does not support resource {resource!r}")

