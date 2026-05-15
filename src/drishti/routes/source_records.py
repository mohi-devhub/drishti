from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from drishti.auth.dependencies import get_current_merchant_id
from drishti.db.repositories import source_records

router = APIRouter(prefix="/api/source_records", tags=["source-records"])

SENSITIVE_KEY_PARTS = (
    "address",
    "authorization",
    "billing",
    "customer",
    "email",
    "first_name",
    "last_name",
    "name",
    "password",
    "phone",
    "secret",
    "shipping",
    "token",
)


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
        "payload": _redact_payload(record["payload"]),
        "payload_redacted": True,
        "payload_hash": record["payload_hash"],
        "sync_run_id": str(record["sync_run_id"]) if record["sync_run_id"] else None,
    }


def _redact_payload(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if any(part in key_text for part in SENSITIVE_KEY_PARTS):
                redacted[key] = "[redacted]"
            else:
                redacted[key] = _redact_payload(item)
        return redacted
    if isinstance(value, list):
        return [_redact_payload(item) for item in value]
    return value
