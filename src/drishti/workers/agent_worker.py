from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from drishti.agents.rto_shipping_margin.agent import run_worker
from drishti.db.session import set_merchant_context_for_worker


async def run_rto_shipping_margin_agent(
    ctx: dict[str, Any],
    merchant_id: str,
    trigger: str = "scheduled",
) -> dict:
    merchant_uuid = UUID(merchant_id)
    async with ctx["db_sessionmaker"]() as session:
        await set_merchant_context_for_worker(session, merchant_uuid)
        result = await run_worker(session, merchant_id=merchant_uuid, trigger=trigger)
        await session.commit()
        return result


async def agent_daily_run(ctx: dict[str, Any], merchant_id: str) -> dict:
    delay_seconds = hash(merchant_id) % 14400
    await asyncio.sleep(delay_seconds)
    return await run_rto_shipping_margin_agent(ctx, merchant_id, trigger="scheduled")
