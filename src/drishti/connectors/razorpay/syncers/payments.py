from __future__ import annotations

from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from drishti.connectors.base.resource_syncer import upsert_domain_row
from drishti.connectors.razorpay.syncers.common import (
    RazorpayListSyncer,
    epoch_to_datetime,
    first_present,
    paise,
)
from drishti.db.repositories import order_links


class RazorpayPaymentsSyncer(RazorpayListSyncer):
    resource: ClassVar[str] = "payments"
    path = "/v1/payments"

    def source_record_id(self, raw: dict[str, Any]) -> str:
        return str(raw["id"])

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        notes = raw.get("notes") or {}
        amount = paise(raw.get("amount")) or 0
        fee = paise(raw.get("fee"))
        tax = paise(raw.get("tax"))
        return {
            "status": _payment_status(raw),
            "method": raw.get("method") or "unknown",
            "amount_paise": amount,
            "fee_paise": fee,
            "tax_paise": tax,
            "net_paise": amount - (fee or 0),
            "currency": raw.get("currency") or "INR",
            "captured_at": epoch_to_datetime(first_present(raw.get("captured_at"), raw.get("created_at"))),
            "extras": {
                "order_id": first_present(notes.get("shopify_order_id"), notes.get("order_id"), raw.get("order_id")),
                "razorpay_order_id": raw.get("order_id"),
                "notes": notes,
            },
        }

    async def upsert(
        self,
        session: AsyncSession,
        normalized: dict[str, Any],
        *,
        raw_record_id: UUID,
        sync_run_id: UUID,
    ) -> UUID:
        source_record_id = normalized.pop("source_record_id")
        payment_id = await upsert_domain_row(
            session,
            table="payments",
            merchant_id=self.connector.connection.merchant_id,
            source=self.connector.source,
            source_record_id=source_record_id,
            raw_record_id=raw_record_id,
            sync_run_id=sync_run_id,
            values=normalized,
        )
        order_ref = normalized.get("extras", {}).get("order_id")
        if order_ref:
            await order_links.link_order_to_payment(
                session,
                merchant_id=self.connector.connection.merchant_id,
                order_reference=str(order_ref),
                payment_id=payment_id,
            )
        return payment_id


def _payment_status(raw: dict[str, Any]) -> str:
    status = str(raw.get("status") or "").lower()
    if status in {"created", "authorized", "captured", "failed", "refunded"}:
        return status
    return "captured" if raw.get("captured") else "created"
