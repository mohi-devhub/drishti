from __future__ import annotations

from typing import Any
from uuid import UUID

from drishti.config import get_settings
from drishti.connectors.registry import build_connector
from drishti.db.repositories import connections, source_records, sync_runs
from drishti.db.session import set_merchant_context_for_worker


async def normalize_shopify(ctx: dict[str, Any], merchant_id: str, source_record_id: str) -> dict:
    return await normalize_source_record(ctx, merchant_id, "shopify", source_record_id)


async def normalize_shiprocket(ctx: dict[str, Any], merchant_id: str, source_record_id: str) -> dict:
    return await normalize_source_record(ctx, merchant_id, "shiprocket", source_record_id)


async def normalize_razorpay(ctx: dict[str, Any], merchant_id: str, source_record_id: str) -> dict:
    return await normalize_source_record(ctx, merchant_id, "razorpay", source_record_id)


async def normalize_source_record(
    ctx: dict[str, Any],
    merchant_id: str,
    source: str,
    source_record_id: str,
) -> dict:
    merchant_uuid = UUID(merchant_id)
    raw_record_uuid = UUID(source_record_id)
    sessionmaker = ctx["db_sessionmaker"]
    settings = ctx.get("settings") or get_settings()

    async with sessionmaker() as session:
        await set_merchant_context_for_worker(session, merchant_uuid)
        raw_record = await source_records.get_by_id(
            session,
            merchant_id=merchant_uuid,
            source_record_id=raw_record_uuid,
        )
        if raw_record is None:
            raise ValueError(f"source_record {source_record_id} not found")

        connection = await connections.get_active_by_source(
            session,
            merchant_id=merchant_uuid,
            source=source,
        )
        if connection is None:
            raise ValueError(f"No active {source} connection for merchant {merchant_id}")

        connector = build_connector(connection, settings=settings, redis=ctx.get("redis"))
        syncer = connector.syncer(raw_record["resource"])
        normalized = syncer.normalize(raw_record["payload"])
        normalized["source_record_id"] = raw_record["source_record_id"]
        normalized_id = await syncer.upsert(
            session,
            normalized,
            raw_record_id=raw_record_uuid,
            sync_run_id=raw_record["sync_run_id"],
        )
        if raw_record["sync_run_id"] is not None:
            await sync_runs.record_metrics(
                session,
                merchant_id=merchant_uuid,
                sync_run_id=raw_record["sync_run_id"],
                records_normalized=1,
            )
        await session.commit()

    return {"normalized_id": str(normalized_id)}
