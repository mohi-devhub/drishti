from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from drishti.agents.rto_shipping_margin.agent import input_snapshot
from drishti.auth.dependencies import get_current_merchant_id
from drishti.db.repositories import agent_runs
from drishti.rate_limit import check_rate_limit

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentRunResponse(BaseModel):
    run_id: UUID
    status: str
    findings_count: int = 0


@router.post("/rto_shipping_margin/runs")
async def run_rto_shipping_margin_agent(
    request: Request,
    merchant_id=Depends(get_current_merchant_id),
) -> AgentRunResponse:
    session: AsyncSession = request.state.db
    check_rate_limit(
        request,
        merchant_id=merchant_id,
        bucket="agent_runs",
        limit=30 if request.app.state.settings.environment == "local" else 5,
        window_seconds=60 if request.app.state.settings.environment == "local" else 300,
    )
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent queue is unavailable",
        )
    snapshot = await input_snapshot(session, merchant_id=merchant_id)
    run_id = await agent_runs.create_queued(
        session,
        merchant_id=merchant_id,
        trigger="manual",
        input_snapshot=snapshot,
    )
    await session.commit()
    await redis.enqueue_job(
        "run_rto_shipping_margin_agent",
        str(merchant_id),
        "manual",
        str(run_id),
    )
    return AgentRunResponse(run_id=run_id, status="queued")


@router.get("/rto_shipping_margin/runs/{run_id}", response_model=AgentRunResponse)
async def get_rto_shipping_margin_agent_run(
    run_id: UUID,
    request: Request,
    merchant_id=Depends(get_current_merchant_id),
) -> AgentRunResponse:
    session: AsyncSession = request.state.db
    row = await agent_runs.get_run(session, merchant_id=merchant_id, run_id=run_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
    return AgentRunResponse(
        run_id=row["id"],
        status=row["status"],
        findings_count=row["findings_count"] or 0,
    )
