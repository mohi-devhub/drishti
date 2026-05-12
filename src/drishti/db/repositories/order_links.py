from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def link_order_to_shipment(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    order_reference: str,
    shipment_id: UUID,
    confidence: float = 1.0,
) -> UUID | None:
    order_id = await _find_order_id(session, merchant_id=merchant_id, order_reference=order_reference)
    if order_id is None:
        return None
    return await _upsert_link(
        session,
        merchant_id=merchant_id,
        order_id=order_id,
        shipment_id=shipment_id,
        payment_id=None,
        linkage_method="order_id_match",
        confidence=confidence,
    )


async def link_order_to_payment(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    order_reference: str,
    payment_id: UUID,
    confidence: float = 1.0,
) -> UUID | None:
    order_id = await _find_order_id(session, merchant_id=merchant_id, order_reference=order_reference)
    if order_id is None:
        return None
    return await _upsert_link(
        session,
        merchant_id=merchant_id,
        order_id=order_id,
        shipment_id=None,
        payment_id=payment_id,
        linkage_method="metadata_match",
        confidence=confidence,
    )


async def _find_order_id(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    order_reference: str,
) -> UUID | None:
    result = await session.execute(
        text(
            """
            SELECT id
            FROM orders
            WHERE merchant_id = :merchant_id
              AND (
                source_record_id = :order_reference
                OR extras->>'name' = :order_reference
                OR extras->>'order_number' = :order_reference
              )
            ORDER BY updated_at DESC
            LIMIT 1
            """
        ),
        {"merchant_id": str(merchant_id), "order_reference": order_reference},
    )
    return result.scalar_one_or_none()


async def _upsert_link(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    order_id: UUID,
    shipment_id: UUID | None,
    payment_id: UUID | None,
    linkage_method: str,
    confidence: float,
) -> UUID:
    set_columns = ["linkage_method = EXCLUDED.linkage_method", "confidence = EXCLUDED.confidence", "updated_at = now()"]
    if shipment_id is not None:
        set_columns.append("shipment_id = EXCLUDED.shipment_id")
    if payment_id is not None:
        set_columns.append("payment_id = EXCLUDED.payment_id")
    result = await session.execute(
        text(
            f"""
            INSERT INTO order_links (
                merchant_id, order_id, shipment_id, payment_id,
                linkage_method, confidence, created_at, updated_at
            )
            VALUES (
                :merchant_id, :order_id, :shipment_id, :payment_id,
                :linkage_method, :confidence, now(), now()
            )
            ON CONFLICT (merchant_id, order_id)
            DO UPDATE SET {", ".join(set_columns)}
            RETURNING id
            """
        ),
        {
            "merchant_id": str(merchant_id),
            "order_id": str(order_id),
            "shipment_id": str(shipment_id) if shipment_id else None,
            "payment_id": str(payment_id) if payment_id else None,
            "linkage_method": linkage_method,
            "confidence": confidence,
        },
    )
    return result.scalar_one()
