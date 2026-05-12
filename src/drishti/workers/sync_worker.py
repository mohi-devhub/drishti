from __future__ import annotations

from typing import Any
from uuid import UUID

from drishti.config import get_settings
from drishti.connectors.registry import build_connector
from drishti.db.repositories import connections, sync_runs
from drishti.db.session import set_merchant_context_for_worker


async def sync_shopify_orders(
    ctx: dict[str, Any], merchant_id: str, cursor: dict | None = None
) -> dict:
    return await sync_resource(ctx, merchant_id, "shopify", "orders", cursor=cursor)


async def sync_shopify_customers(
    ctx: dict[str, Any], merchant_id: str, cursor: dict | None = None
) -> dict:
    return await sync_resource(ctx, merchant_id, "shopify", "customers", cursor=cursor)


async def sync_shopify_products(
    ctx: dict[str, Any], merchant_id: str, cursor: dict | None = None
) -> dict:
    return await sync_resource(ctx, merchant_id, "shopify", "products", cursor=cursor)


async def sync_resource(
    ctx: dict[str, Any],
    merchant_id: str,
    source: str,
    resource: str,
    *,
    cursor: dict | None = None,
    trigger: str = "manual",
) -> dict:
    merchant_uuid = UUID(merchant_id)
    sessionmaker = ctx["db_sessionmaker"]
    settings = ctx.get("settings") or get_settings()

    async with sessionmaker() as session:
        await set_merchant_context_for_worker(session, merchant_uuid)
        connection = await connections.get_active_by_source(
            session,
            merchant_id=merchant_uuid,
            source=source,
        )
        if connection is None:
            raise ValueError(f"No active {source} connection for merchant {merchant_id}")

        cursor_before = cursor if cursor is not None else connection.cursors.get(resource)
        sync_run_id = await sync_runs.create(
            session,
            merchant_id=merchant_uuid,
            source=source,
            resource=resource,
            trigger=trigger,
            connection_id=connection.id,
            cursor_before=cursor_before,
        )
        await session.commit()

        try:
            connector = build_connector(connection, settings=settings, redis=ctx.get("redis"))
            syncer = connector.syncer(resource)
            result = await syncer.sync_raw_page_loop(
                session,
                sync_run_id=sync_run_id,
                cursor=cursor_before,
            )
            await connections.update_resource_cursor(
                session,
                merchant_id=merchant_uuid,
                connection_id=connection.id,
                resource=resource,
                cursor=result.cursor_after,
            )
            await sync_runs.record_metrics(
                session,
                merchant_id=merchant_uuid,
                sync_run_id=sync_run_id,
                records_fetched=result.records_fetched,
                api_calls=result.api_calls,
                cursor_after=result.cursor_after,
            )
            await sync_runs.update_status(
                session,
                merchant_id=merchant_uuid,
                sync_run_id=sync_run_id,
                status="completed",
            )
            await session.commit()
        except Exception as exc:
            await sync_runs.update_status(
                session,
                merchant_id=merchant_uuid,
                sync_run_id=sync_run_id,
                status="failed",
                error={"type": type(exc).__name__, "message": str(exc)},
            )
            await session.commit()
            raise

    for raw_record_id in result.raw_record_ids:
        await ctx["redis"].enqueue_job(f"normalize_{source}", merchant_id, str(raw_record_id))

    return {
        "sync_run_id": str(sync_run_id),
        "records_fetched": result.records_fetched,
        "api_calls": result.api_calls,
    }
