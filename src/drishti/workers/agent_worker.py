from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from sqlalchemy import text

from drishti.agents.rto_shipping_margin.agent import run_worker
from drishti.db.session import set_merchant_context_for_worker
from drishti.queue import DEFAULT_QUEUE_NAME


async def run_rto_shipping_margin_agent(
    ctx: dict[str, Any],
    merchant_id: str,
    trigger: str = "scheduled",
    run_id: str | None = None,
) -> dict:
    merchant_uuid = UUID(merchant_id)
    async with ctx["db_sessionmaker"]() as session:
        await set_merchant_context_for_worker(session, merchant_uuid)
        result = await run_worker(
            session,
            merchant_id=merchant_uuid,
            trigger=trigger,
            settings=ctx.get("settings"),
            run_id=UUID(run_id) if run_id else None,
        )
        await session.commit()
        return result


async def agent_daily_run(ctx: dict[str, Any], merchant_id: str) -> dict:
    delay_seconds = hash(merchant_id) % 14400
    await asyncio.sleep(delay_seconds)
    return await run_rto_shipping_margin_agent(ctx, merchant_id, trigger="scheduled")


async def enqueue_daily_agent_runs(ctx: dict[str, Any]) -> dict:
    async with ctx["db_sessionmaker"]() as session:
        result = await session.execute(
            text(
                """
                SELECT id
                FROM merchants
                ORDER BY id
                """
            )
        )
        merchant_ids = [str(row["id"]) for row in result.mappings().all()]

    for merchant_id in merchant_ids:
        await ctx["redis"].enqueue_job(
            "agent_daily_run",
            merchant_id,
            _queue_name=DEFAULT_QUEUE_NAME,
        )
    return {"enqueued": len(merchant_ids)}
