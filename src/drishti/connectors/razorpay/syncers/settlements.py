from __future__ import annotations

from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from drishti.connectors.base.resource_syncer import upsert_domain_row
from drishti.connectors.razorpay.syncers.common import RazorpayListSyncer, epoch_to_datetime, paise


class RazorpaySettlementsSyncer(RazorpayListSyncer):
    resource: ClassVar[str] = "settlements"
    path = "/v1/settlements"

    def source_record_id(self, raw: dict[str, Any]) -> str:
        return str(raw["id"])

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": raw.get("status") or "processed",
            "amount_paise": paise(raw.get("amount")) or 0,
            "fees_paise": paise(raw.get("fees")),
            "tax_paise": paise(raw.get("tax")),
            "utr": raw.get("utr"),
            "settled_at": epoch_to_datetime(raw.get("created_at")),
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
        return await upsert_domain_row(
            session,
            table="settlements",
            merchant_id=self.connector.connection.merchant_id,
            source=self.connector.source,
            source_record_id=normalized.pop("source_record_id"),
            raw_record_id=raw_record_id,
            sync_run_id=sync_run_id,
            values=normalized,
        )
