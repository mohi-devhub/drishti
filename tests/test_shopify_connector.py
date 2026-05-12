from __future__ import annotations

from uuid import UUID

import pytest

from drishti.connectors.base import ConnectorConnection, MockTransport, NoopRateLimiter
from drishti.connectors.shopify import ShopifyConnector


MERCHANT_ID = UUID("00000000-0000-0000-0000-00000000000a")
CONNECTION_ID = UUID("30000000-0000-0000-0000-000000000001")


def shopify_connector() -> ShopifyConnector:
    return ShopifyConnector(
        ConnectorConnection(
            id=CONNECTION_ID,
            merchant_id=MERCHANT_ID,
            source="shopify",
            auth_payload={
                "shop": "demo-shop.myshopify.com",
                "access_token": "shpat_test",
            },
            cursors={},
        ),
        MockTransport("fixtures/shopify"),
        NoopRateLimiter(),
    )


@pytest.mark.asyncio
async def test_shopify_orders_fetches_fixture_and_normalizes_cod_order() -> None:
    syncer = shopify_connector().syncer("orders")

    page = await syncer.fetch_page(None)
    normalized = syncer.normalize(page.records[0])

    assert page.has_more is False
    assert syncer.source_record_id(page.records[0]) == "5234567890123"
    assert normalized["payment_method"] == "cod"
    assert normalized["status"] == "confirmed"
    assert normalized["total_paise"] == 204800
    assert normalized["shipping_pincode"] == "110001"
    assert normalized["line_items_count"] == 1


@pytest.mark.asyncio
async def test_shopify_customers_and_products_normalize_money_fields() -> None:
    connector = shopify_connector()

    customer_page = await connector.syncer("customers").fetch_page(None)
    customer = connector.syncer("customers").normalize(customer_page.records[0])
    product_page = await connector.syncer("products").fetch_page(None)
    product = connector.syncer("products").normalize(product_page.records[0])

    assert customer["email"] == "customer001@example.test"
    assert customer["total_spent_paise"] == 204800
    assert product["sku"] == "KURTA-BLUE-M"
    assert product["price_paise"] == 99900
    assert product["weight_grams"] == 350

