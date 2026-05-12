from datetime import UTC, datetime
from uuid import UUID

import pytest

from drishti.db.repositories import chat, order_links, source_records, sync_runs

MERCHANT_A = UUID("00000000-0000-0000-0000-00000000000a")
RAW_ID = UUID("10000000-0000-0000-0000-000000000001")
SYNC_RUN_ID = UUID("20000000-0000-0000-0000-000000000001")


class FakeScalarResult:
    def __init__(self, value=None) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value

    def mappings(self):
        return self

    def all(self):
        return []


class FakeSession:
    def __init__(self, value=RAW_ID) -> None:
        self.value = value
        self.calls = []

    async def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return FakeScalarResult(self.value)


def test_payload_hash_is_stable_for_key_order() -> None:
    left = source_records.payload_hash({"id": 1, "nested": {"b": 2, "a": 1}})
    right = source_records.payload_hash({"nested": {"a": 1, "b": 2}, "id": 1})

    assert left == right


@pytest.mark.asyncio
async def test_insert_raw_scopes_insert_to_merchant() -> None:
    session = FakeSession()

    raw_id = await source_records.insert_raw(
        session,
        merchant_id=MERCHANT_A,
        source="shopify",
        resource="orders",
        source_record_id="gid://shopify/Order/1",
        endpoint="GET /admin/api/orders/1.json",
        payload={"id": 1},
        fetched_at=datetime.now(UTC),
    )

    sql, params = session.calls[0]
    assert raw_id == RAW_ID
    assert "INSERT INTO source_records" in sql
    assert params["merchant_id"] == str(MERCHANT_A)
    assert "payload_hash" in params


@pytest.mark.asyncio
async def test_list_for_merchant_keeps_merchant_filter() -> None:
    session = FakeSession()

    await source_records.list_for_merchant(
        session,
        merchant_id=MERCHANT_A,
        source="shopify",
        resource="orders",
    )

    sql, params = session.calls[0]
    assert "WHERE merchant_id = :merchant_id" in sql
    assert "source = :source" in sql
    assert "resource = :resource" in sql
    assert params["merchant_id"] == str(MERCHANT_A)


@pytest.mark.asyncio
async def test_sync_run_updates_are_merchant_scoped() -> None:
    session = FakeSession(SYNC_RUN_ID)

    await sync_runs.update_status(
        session,
        merchant_id=MERCHANT_A,
        sync_run_id=SYNC_RUN_ID,
        status="completed",
    )

    sql, params = session.calls[0]
    assert "UPDATE sync_runs" in sql
    assert "WHERE merchant_id = :merchant_id" in sql
    assert "AND id = :sync_run_id" in sql
    assert params["merchant_id"] == str(MERCHANT_A)


@pytest.mark.asyncio
async def test_order_link_shipment_lookup_and_upsert_are_merchant_scoped() -> None:
    order_id = UUID("40000000-0000-0000-0000-000000000001")
    shipment_id = UUID("50000000-0000-0000-0000-000000000001")
    session = FakeSession(order_id)

    await order_links.link_order_to_shipment(
        session,
        merchant_id=MERCHANT_A,
        order_reference="#1001",
        shipment_id=shipment_id,
    )

    lookup_sql, lookup_params = session.calls[0]
    upsert_sql, upsert_params = session.calls[1]
    assert "FROM orders" in lookup_sql
    assert "WHERE merchant_id = :merchant_id" in lookup_sql
    assert lookup_params["merchant_id"] == str(MERCHANT_A)
    assert "INSERT INTO order_links" in upsert_sql
    assert "ON CONFLICT (merchant_id, order_id)" in upsert_sql
    assert upsert_params["shipment_id"] == str(shipment_id)


@pytest.mark.asyncio
async def test_chat_repository_writes_are_merchant_scoped() -> None:
    session = FakeSession(UUID("60000000-0000-0000-0000-000000000001"))

    await chat.create_session(
        session,
        merchant_id=MERCHANT_A,
        clerk_user_id="user_123",
        title="hello",
    )
    await chat.insert_message(
        session,
        merchant_id=MERCHANT_A,
        session_id=UUID("60000000-0000-0000-0000-000000000001"),
        role="user",
        content="hello",
    )

    create_sql, create_params = session.calls[0]
    message_sql, message_params = session.calls[1]
    update_sql, update_params = session.calls[2]
    assert "INSERT INTO chat_sessions" in create_sql
    assert create_params["merchant_id"] == str(MERCHANT_A)
    assert "INSERT INTO chat_messages" in message_sql
    assert message_params["merchant_id"] == str(MERCHANT_A)
    assert "WHERE merchant_id = :merchant_id" in update_sql
    assert update_params["merchant_id"] == str(MERCHANT_A)


@pytest.mark.asyncio
async def test_tool_call_repository_serializes_result_and_validation_state() -> None:
    session = FakeSession(UUID("70000000-0000-0000-0000-000000000001"))

    await chat.create_tool_call(
        session,
        merchant_id=MERCHANT_A,
        caller="chat",
        caller_id=None,
        tool_name="query_orders",
        args={"limit": 1},
        result={"rows": []},
        result_id="tr_abc",
        validation_status="passed",
    )

    sql, params = session.calls[0]
    assert "INSERT INTO tool_calls" in sql
    assert "CAST(:args AS jsonb)" in sql
    assert params["merchant_id"] == str(MERCHANT_A)
    assert params["result_id"] == "tr_abc"
    assert params["validation_status"] == "passed"
