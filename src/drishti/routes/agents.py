from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from drishti.agents.rto_shipping_margin.agent import input_snapshot
from drishti.auth.dependencies import get_current_merchant_id
from drishti.db.repositories import agent_runs
from drishti.queue import DEFAULT_QUEUE_NAME
from drishti.rate_limit import check_rate_limit

router = APIRouter(prefix="/agents", tags=["agents"])

KNOWN_DUTIES = {
    "cod_rto_risk",
    "courier_margin_drift",
    "delayed_prepaid",
    "refund_shipping_mismatch",
}


class AgentRunResponse(BaseModel):
    run_id: UUID
    status: str
    findings_count: int = 0


class AgentRunCancelResponse(BaseModel):
    run_id: UUID
    status: str


class DutyConfigUpdate(BaseModel):
    enabled: bool
    config: dict[str, object] = Field(default_factory=dict)


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
        _queue_name=DEFAULT_QUEUE_NAME,
    )
    return AgentRunResponse(run_id=run_id, status="queued")


@router.post("/rto_shipping_margin/runs/{run_id}/cancel", response_model=AgentRunCancelResponse)
async def cancel_rto_shipping_margin_agent_run(
    run_id: UUID,
    request: Request,
    merchant_id=Depends(get_current_merchant_id),
) -> AgentRunCancelResponse:
    session: AsyncSession = request.state.db
    row = await agent_runs.get_run(session, merchant_id=merchant_id, run_id=run_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
    if row["status"] not in {"queued", "running"}:
        return AgentRunCancelResponse(run_id=run_id, status=row["status"])
    cancelled = await agent_runs.cancel_run(session, merchant_id=merchant_id, run_id=run_id)
    await session.commit()
    return AgentRunCancelResponse(run_id=run_id, status="cancelled" if cancelled else row["status"])


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


@router.get("/rto_shipping_margin/duty-configs")
async def list_rto_shipping_margin_duty_configs(
    request: Request,
    merchant_id=Depends(get_current_merchant_id),
) -> dict:
    session: AsyncSession = request.state.db
    rows = await agent_runs.list_duty_configs(session, merchant_id=merchant_id)
    existing = {row["duty"]: row for row in rows}
    configs = []
    for duty in sorted(KNOWN_DUTIES):
        row = existing.get(duty)
        configs.append(
            {
                "duty": duty,
                "enabled": True if row is None else row["enabled"],
                "config": {} if row is None else row["config"],
                "updated_at": None if row is None else row["updated_at"].isoformat(),
            }
        )
    return {"configs": configs}


@router.patch("/rto_shipping_margin/duty-configs/{duty}")
async def update_rto_shipping_margin_duty_config(
    duty: str,
    body: DutyConfigUpdate,
    request: Request,
    merchant_id=Depends(get_current_merchant_id),
) -> dict:
    if duty not in KNOWN_DUTIES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Duty not found")
    session: AsyncSession = request.state.db
    row = await agent_runs.upsert_duty_config(
        session,
        merchant_id=merchant_id,
        duty=duty,
        enabled=body.enabled,
        config=body.config,
    )
    await session.commit()
    return {
        "config": {
            "duty": row["duty"],
            "enabled": row["enabled"],
            "config": row["config"],
            "updated_at": row["updated_at"].isoformat(),
        }
    }
