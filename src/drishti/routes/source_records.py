from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from drishti.auth.dependencies import get_current_merchant_id
from drishti.db.repositories import source_records

router = APIRouter(prefix="/api/source_records", tags=["source-records"])


@router.get("/{source_record_id}")
async def get_source_record(
    source_record_id: UUID,
    request: Request,
    merchant_id=Depends(get_current_merchant_id),
) -> dict:
    session: AsyncSession = request.state.db
    record = await source_records.get_by_id(
        session,
        merchant_id=merchant_id,
        source_record_id=source_record_id,
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source record not found")
    return {
        "id": str(record["id"]),
        "source": record["source"],
        "resource": record["resource"],
        "source_record_id": record["source_record_id"],
        "endpoint": record["endpoint"],
        "fetched_at": record["fetched_at"].isoformat() if record["fetched_at"] else None,
        "payload": record["payload"],
        "payload_hash": record["payload_hash"],
        "sync_run_id": str(record["sync_run_id"]) if record["sync_run_id"] else None,
    }
