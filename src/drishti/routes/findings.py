from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from drishti.auth.dependencies import get_current_merchant_id
from drishti.db.repositories import agent_runs

router = APIRouter(prefix="/api/findings", tags=["findings"])

LIFECYCLE_STATUSES = {"open", "acknowledged", "actioned", "dismissed"}


class FindingLifecycleUpdate(BaseModel):
    lifecycle_status: str


@router.get("")
async def list_agent_findings(
    request: Request,
    merchant_id=Depends(get_current_merchant_id),
    limit: int = 50,
    severity: str | None = None,
    lifecycle_status: str | None = None,
    q: str | None = None,
    sort: str = "newest",
) -> dict:
    session: AsyncSession = request.state.db
    run, rows = await agent_runs.list_latest_findings(
        session,
        merchant_id=merchant_id,
        limit=limit,
        severity=_none_if_all(severity),
        lifecycle_status=_none_if_all(lifecycle_status),
        query=q.strip() if q and q.strip() else None,
        sort=sort,
    )
    return {
        "run": _serialize_run(run) if run else None,
        "findings": [_serialize(row) for row in rows],
    }


@router.get("/{finding_id}")
async def get_agent_finding(
    finding_id: UUID,
    request: Request,
    merchant_id=Depends(get_current_merchant_id),
) -> dict:
    session: AsyncSession = request.state.db
    row = await agent_runs.get_finding(session, merchant_id=merchant_id, finding_id=finding_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    return {"finding": _serialize(row)}


@router.patch("/{finding_id}")
async def update_agent_finding(
    finding_id: UUID,
    body: FindingLifecycleUpdate,
    request: Request,
    merchant_id=Depends(get_current_merchant_id),
) -> dict:
    if body.lifecycle_status not in LIFECYCLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported lifecycle status",
        )
    session: AsyncSession = request.state.db
    row = await agent_runs.update_finding_lifecycle(
        session,
        merchant_id=merchant_id,
        finding_id=finding_id,
        lifecycle_status=body.lifecycle_status,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    await session.commit()
    return {"finding": _serialize(row)}


def _serialize(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "run_id": str(row["run_id"]),
        "duty": row["duty"],
        "finding_type": row["finding_type"],
        "severity": row["severity"],
        "lifecycle_status": row.get("lifecycle_status", "open"),
        "fingerprint": row.get("fingerprint"),
        "confidence": float(row["confidence"]) if row["confidence"] is not None else None,
        "evidence_row_ids": list(row["evidence_row_ids"] or []),
        "estimated_saving_inr_low": row["estimated_saving_inr_low"],
        "estimated_saving_inr_high": row["estimated_saving_inr_high"],
        "narrative": row["narrative"],
        "narrative_status": row["narrative_status"],
        "proposed_action": row["proposed_action"],
        "citations": row["citations"] if "citations" in row else [],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


def _serialize_run(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "trigger": row["trigger"],
        "status": row["status"],
        "findings_count": row["findings_count"],
        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


def _none_if_all(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return None if value == "" or value == "all" else value
