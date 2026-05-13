from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from drishti.auth.dependencies import get_current_merchant_id
from drishti.db.repositories import agent_runs

router = APIRouter(prefix="/api/findings", tags=["findings"])


@router.get("")
async def list_agent_findings(
    request: Request,
    merchant_id=Depends(get_current_merchant_id),
    limit: int = 50,
) -> dict:
    session: AsyncSession = request.state.db
    rows = await agent_runs.list_findings(session, merchant_id=merchant_id, limit=limit)
    return {"findings": [_serialize(row) for row in rows]}


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


def _serialize(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "run_id": str(row["run_id"]),
        "duty": row["duty"],
        "finding_type": row["finding_type"],
        "severity": row["severity"],
        "confidence": float(row["confidence"]) if row["confidence"] is not None else None,
        "evidence_row_ids": list(row["evidence_row_ids"] or []),
        "estimated_saving_inr_low": row["estimated_saving_inr_low"],
        "estimated_saving_inr_high": row["estimated_saving_inr_high"],
        "narrative": row["narrative"],
        "narrative_status": row["narrative_status"],
        "proposed_action": row["proposed_action"],
        "citations": row["citations"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }
