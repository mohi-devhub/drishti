from __future__ import annotations

from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from drishti.connectors.base.resource_syncer import upsert_domain_row
from drishti.connectors.razorpay.syncers.common import RazorpayListSyncer, epoch_to_datetime, paise


class RazorpayRefundsSyncer(RazorpayListSyncer):
    resource: ClassVar[str] = "refunds"
    path = "/v1/refunds"

    def source_record_id(self, raw: dict[str, Any]) -> str:
        return str(raw["id"])

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "payment_source_record_id": raw.get("payment_id"),
            "status": raw.get("status") or "processed",
            "amount_paise": paise(raw.get("amount")) or 0,
            "reason": raw.get("notes", {}).get("reason") if isinstance(raw.get("notes"), dict) else None,
            "processed_at": epoch_to_datetime(raw.get("created_at")),
            "extras": raw,
        }

    async def upsert(
        self,
        session: AsyncSession,
        normalized: dict[str, Any],
        *,
        raw_record_id: UUID,
        sync_run_id: UUID,
    ) -> UUID:
        payment_source_record_id = normalized.pop("payment_source_record_id")
        result = await session.execute(
            text(
                """
                SELECT id
                FROM payments
                WHERE merchant_id = :merchant_id
                  AND source = 'razorpay'
                  AND source_record_id = :source_record_id
                """
            ),
            {
                "merchant_id": str(self.connector.connection.merchant_id),
                "source_record_id": payment_source_record_id,
            },
        )
        payment_id = result.scalar_one()
        normalized["payment_id"] = payment_id
        return await upsert_domain_row(
            session,
            table="refunds",
            merchant_id=self.connector.connection.merchant_id,
            source=self.connector.source,
            source_record_id=normalized.pop("source_record_id"),
            raw_record_id=raw_record_id,
            sync_run_id=sync_run_id,
            values=normalized,
        )
