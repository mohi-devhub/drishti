from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from drishti.agents.rto_shipping_margin.agent import run_worker
from drishti.auth.dependencies import get_current_merchant_id

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/rto_shipping_margin/runs")
async def run_rto_shipping_margin_agent(
    request: Request,
    merchant_id=Depends(get_current_merchant_id),
) -> dict:
    session: AsyncSession = request.state.db
    return await run_worker(
        session,
        merchant_id=merchant_id,
        trigger="manual",
        settings=request.app.state.settings,
    )
