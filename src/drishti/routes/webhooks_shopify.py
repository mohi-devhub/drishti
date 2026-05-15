from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status

from drishti.config import get_settings
from drishti.db.repositories import connections, source_records, webhook_deliveries
from drishti.db.session import set_merchant_context
from drishti.webhooks.shopify import resource_from_topic, verify_hmac

router = APIRouter(prefix="/webhooks/shopify", tags=["webhooks"])


@router.post("/{topic:path}")
async def shopify_webhook(topic: str, request: Request) -> dict:
    settings = get_settings()
    body = await request.body()
    if not verify_hmac(
        body=body,
        header=request.headers.get("x-shopify-hmac-sha256"),
        secret=settings.shopify_webhook_secret,
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Shopify HMAC")

    payload = json.loads(body.decode("utf-8"))
    external_id = request.headers.get("x-shopify-webhook-id") or hashlib.sha256(body).hexdigest()
    payload_hash = hashlib.sha256(body).hexdigest()
    shop_domain = request.headers.get("x-shopify-shop-domain")
    if not shop_domain:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Shopify shop domain header",
        )
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Normalize queue is unavailable",
        )
    sessionmaker = request.app.state.db_sessionmaker
    async with sessionmaker() as session:
        async with session.begin():
            connection = await connections.get_active_shopify_by_shop_domain(
                session,
                shop_domain=shop_domain,
            )
            if connection is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No active Shopify connection for shop",
                )
            merchant_id = connection.merchant_id
            await set_merchant_context(session, merchant_id)
            inserted = await webhook_deliveries.insert_once(
                session,
                merchant_id=merchant_id,
                source="shopify",
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
                source="shopify",
                resource=resource_from_topic(topic),
                source_record_id=str(payload.get("id", external_id)),
                endpoint=f"POST /webhooks/shopify/{topic}",
                payload=payload,
                fetched_at=datetime.now(UTC),
            )
    await redis.enqueue_job("normalize_shopify", str(merchant_id), str(raw_record_id))
    return {"status": "accepted", "source_record_id": str(raw_record_id)}
