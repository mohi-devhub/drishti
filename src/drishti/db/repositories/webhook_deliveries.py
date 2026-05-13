from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def insert_once(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    source: str,
    external_id: str,
    topic: str,
    payload_hash: str,
    received_at: datetime,
) -> bool:
    result = await session.execute(
        text(
            """
            INSERT INTO webhook_deliveries (
                merchant_id, source, external_id, topic, received_at, payload_hash
            )
            VALUES (
                :merchant_id, :source, :external_id, :topic, :received_at, :payload_hash
            )
            ON CONFLICT (merchant_id, source, external_id) DO NOTHING
            RETURNING id
            """
        ),
        {
            "merchant_id": str(merchant_id),
            "source": source,
            "external_id": external_id,
            "topic": topic,
            "received_at": received_at,
            "payload_hash": payload_hash,
        },
    )
    return result.scalar_one_or_none() is not None
