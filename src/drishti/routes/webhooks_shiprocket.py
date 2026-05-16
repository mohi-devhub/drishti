from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status

from drishti.config import get_settings
from drishti.db.repositories import connections, source_records, webhook_deliveries
from drishti.db.session import set_merchant_context
from drishti.queue import DEFAULT_QUEUE_NAME
from drishti.webhooks.shiprocket import resource_from_payload, verify_secret

router = APIRouter(prefix="/webhooks/shiprocket", tags=["webhooks"])


@router.post("/{topic:path}")
async def shiprocket_webhook(topic: str, request: Request) -> dict:
    settings = get_settings()
    if not verify_secret(
        header=request.headers.get("x-shiprocket-webhook-secret")
        or request.headers.get("x-drishti-webhook-secret"),
        secret=settings.shiprocket_webhook_secret,
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Shiprocket webhook secret")
    body = await request.body()
    payload = json.loads(body.decode("utf-8"))
    account_id = (
        request.headers.get("x-shiprocket-company-id")
        or payload.get("company_id")
        or payload.get("account_id")
    )
    if not account_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Shiprocket account id")

    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Normalize queue is unavailable")

    resource = resource_from_payload(payload, topic)
    external_id = str(
        request.headers.get("x-shiprocket-webhook-id")
        or payload.get("id")
        or payload.get("shipment_id")
        or payload.get("awb_code")
        or payload.get("awb")
        or hashlib.sha256(body).hexdigest()
    )
    payload_hash = hashlib.sha256(body).hexdigest()
    sessionmaker = request.app.state.db_sessionmaker
    async with sessionmaker() as session:
        async with session.begin():
            connection = await connections.get_active_by_external_account(
                session,
                source="shiprocket",
                account_key="account_id",
                account_id=str(account_id),
            )
            if connection is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No active Shiprocket connection for account",
                )
            merchant_id = connection.merchant_id
            await set_merchant_context(session, merchant_id)
            inserted = await webhook_deliveries.insert_once(
                session,
                merchant_id=merchant_id,
                source="shiprocket",
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
                source="shiprocket",
                resource=resource,
                source_record_id=external_id,
                endpoint=f"POST /webhooks/shiprocket/{topic}",
                payload=payload,
                fetched_at=datetime.now(UTC),
            )
    await redis.enqueue_job(
        "normalize_shiprocket",
        str(merchant_id),
        str(raw_record_id),
        _queue_name=DEFAULT_QUEUE_NAME,
    )
    return {"status": "accepted", "source_record_id": str(raw_record_id)}
