from __future__ import annotations

from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from drishti.connectors.base.resource_syncer import upsert_domain_row
from drishti.connectors.shopify.syncers.common import (
    ShopifyResourceSyncer,
    admin_path,
    money_to_paise,
    shopify_id,
)


class ShopifyCustomersSyncer(ShopifyResourceSyncer):
    resource: ClassVar[str] = "customers"
    response_key = "customers"
    path = admin_path("customers")

    def source_record_id(self, raw: dict[str, Any]) -> str:
        return shopify_id(raw)

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "email": raw.get("email"),
            "phone": raw.get("phone"),
            "first_name": raw.get("first_name"),
            "last_name": raw.get("last_name"),
            "total_spent_paise": money_to_paise(raw.get("total_spent")),
            "currency": raw.get("currency") or "INR",
            "extras": {
                "shopify_created_at": raw.get("created_at"),
                "shopify_updated_at": raw.get("updated_at"),
                "state": raw.get("state"),
                "tags": raw.get("tags"),
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
        return await upsert_domain_row(
            session,
            table="customers",
            merchant_id=self.connector.connection.merchant_id,
            source=self.connector.source,
            source_record_id=normalized.pop("source_record_id"),
            raw_record_id=raw_record_id,
            sync_run_id=sync_run_id,
            values=normalized,
        )

