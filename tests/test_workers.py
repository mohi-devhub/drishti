from __future__ import annotations

from uuid import UUID

import pytest

from drishti.db.repositories import connections
from drishti.workers.sync_worker import sync_razorpay_payments, sync_shiprocket_shipments, sync_shopify_orders


MERCHANT_ID = UUID("00000000-0000-0000-0000-00000000000a")
CONNECTION_ID = UUID("30000000-0000-0000-0000-000000000001")


class FakeResult:
    def __init__(self, row=None) -> None:
        self.row = row

    def mappings(self):
        return self

    def one_or_none(self):
        return self.row


class FakeSession:
    def __init__(self) -> None:
        self.calls = []

    async def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return FakeResult()


def test_worker_entrypoint_names_are_resource_specific() -> None:
    assert sync_shopify_orders.__name__ == "sync_shopify_orders"
    assert sync_shiprocket_shipments.__name__ == "sync_shiprocket_shipments"
    assert sync_razorpay_payments.__name__ == "sync_razorpay_payments"


@pytest.mark.asyncio
async def test_connection_lookup_scopes_by_merchant_and_source() -> None:
    session = FakeSession()

    await connections.get_active_by_source(
        session,
        merchant_id=MERCHANT_ID,
        source="shopify",
    )

    sql, params = session.calls[0]
    assert "WHERE merchant_id = :merchant_id" in sql
    assert "AND source = :source" in sql
    assert "AND status = 'active'" in sql
    assert params == {"merchant_id": str(MERCHANT_ID), "source": "shopify"}
