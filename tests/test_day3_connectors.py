from __future__ import annotations

from uuid import UUID

import pytest

from drishti.connectors.base import ConnectorConnection, MockTransport, NoopRateLimiter
from drishti.connectors.razorpay import RazorpayConnector
from drishti.connectors.shiprocket import ShiprocketConnector


MERCHANT_ID = UUID("00000000-0000-0000-0000-00000000000a")
SHIPROCKET_CONNECTION_ID = UUID("30000000-0000-0000-0000-000000000002")
RAZORPAY_CONNECTION_ID = UUID("30000000-0000-0000-0000-000000000003")


def shiprocket_connector() -> ShiprocketConnector:
    return ShiprocketConnector(
        ConnectorConnection(
            id=SHIPROCKET_CONNECTION_ID,
            merchant_id=MERCHANT_ID,
            source="shiprocket",
            auth_payload={"token": "shiprocket_test_token"},
            cursors={},
        ),
        MockTransport("fixtures/shiprocket"),
        NoopRateLimiter(),
    )


def razorpay_connector() -> RazorpayConnector:
    return RazorpayConnector(
        ConnectorConnection(
            id=RAZORPAY_CONNECTION_ID,
            merchant_id=MERCHANT_ID,
            source="razorpay",
            auth_payload={"key_id": "rzp_test_key", "key_secret": "secret"},
            cursors={},
        ),
        MockTransport("fixtures/razorpay"),
        NoopRateLimiter(),
    )


@pytest.mark.asyncio
async def test_shiprocket_shipments_fetch_and_normalize() -> None:
    syncer = shiprocket_connector().syncer("shipments")

    page = await syncer.fetch_page(None)
    delivered = syncer.normalize(page.records[0])
    rto = syncer.normalize(page.records[1])

    assert page.has_more is False
    assert syncer.source_record_id(page.records[0]) == "91001"
    assert delivered["status"] == "delivered"
    assert delivered["freight_paise"] == 8250
    assert delivered["weight_grams"] == 450
    assert delivered["extras"]["order_id"] == "#1001"
    assert rto["status"] == "rto_initiated"
    assert syncer.follow_up_sync_jobs(page.records[0]) == []
    assert syncer.follow_up_sync_jobs(page.records[1]) == [
        ("tracking", {"awb_code": "AWB987654321"})
    ]


@pytest.mark.asyncio
async def test_shiprocket_tracking_fetch_and_normalize() -> None:
    syncer = shiprocket_connector().syncer("tracking")

    page = await syncer.fetch_page({"awb_code": "AWB123456789"})
    event = syncer.normalize(page.records[-1])

    assert len(page.records) == 2
    assert event["awb_code"] == "AWB123456789"
    assert event["event_status"] == "delivered"
    assert event["location"] == "Delhi"


@pytest.mark.asyncio
async def test_razorpay_resources_fetch_and_normalize() -> None:
    connector = razorpay_connector()

    payment_page = await connector.syncer("payments").fetch_page(None)
    payment = connector.syncer("payments").normalize(payment_page.records[0])
    refund_page = await connector.syncer("refunds").fetch_page(None)
    refund = connector.syncer("refunds").normalize(refund_page.records[0])
    settlement_page = await connector.syncer("settlements").fetch_page(None)
    settlement = connector.syncer("settlements").normalize(settlement_page.records[0])

    assert payment["status"] == "captured"
    assert payment["amount_paise"] == 204800
    assert payment["net_paise"] == 199967
    assert payment["extras"]["order_id"] == "#1001"
    assert refund["payment_source_record_id"] == "pay_demo_1001"
    assert refund["amount_paise"] == 49900
    assert settlement["utr"] == "UTRDEMO20260513"
