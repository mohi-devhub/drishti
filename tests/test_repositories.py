from datetime import UTC, datetime
from uuid import UUID

import pytest

from drishti.db.repositories import source_records, sync_runs

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
