from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status

from drishti.config import get_settings
from drishti.db.repositories import connections, source_records, webhook_deliveries
from drishti.db.session import set_merchant_context
from drishti.queue import DEFAULT_QUEUE_NAME
from drishti.webhooks.razorpay import resource_and_record, verify_signature

router = APIRouter(prefix="/webhooks/razorpay", tags=["webhooks"])


@router.post("")
async def razorpay_webhook(request: Request) -> dict:
    settings = get_settings()
    body = await request.body()
    if not verify_signature(
        body=body,
        header=request.headers.get("x-razorpay-signature"),
        secret=settings.razorpay_webhook_secret,
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Razorpay signature")
    payload = json.loads(body.decode("utf-8"))
    account_id = (
        request.headers.get("x-razorpay-account-id")
        or payload.get("account_id")
        or payload.get("account")
    )
    if not account_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Razorpay account id")

    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Normalize queue is unavailable")

    resource, record = resource_and_record(payload)
    external_id = str(payload.get("id") or record.get("id") or hashlib.sha256(body).hexdigest())
    payload_hash = hashlib.sha256(body).hexdigest()
    topic = str(payload.get("event") or resource)
    sessionmaker = request.app.state.db_sessionmaker
    async with sessionmaker() as session:
        async with session.begin():
            connection = await connections.get_active_by_external_account(
                session,
                source="razorpay",
                account_key="account_id",
                account_id=str(account_id),
            )
            if connection is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No active Razorpay connection for account",
                )
            merchant_id = connection.merchant_id
            await set_merchant_context(session, merchant_id)
            inserted = await webhook_deliveries.insert_once(
                session,
                merchant_id=merchant_id,
                source="razorpay",
                external_id=external_id,
                topic=topic,
                payload_hash=payload_hash,
                received_at=datetime.now(UTC),
            )
            if not inserted:
                return {"status": "duplicate"}
            raw_record_id = await source_records.insert_raw(
                session,
                merchant_id=merchant_id,
                source="razorpay",
                resource=resource,
                source_record_id=str(record.get("id", external_id)),
                endpoint="POST /webhooks/razorpay",
                payload=record,
                fetched_at=datetime.now(UTC),
            )
    await redis.enqueue_job(
        "normalize_razorpay",
        str(merchant_id),
        str(raw_record_id),
        _queue_name=DEFAULT_QUEUE_NAME,
    )
    return {"status": "accepted", "source_record_id": str(raw_record_id)}
