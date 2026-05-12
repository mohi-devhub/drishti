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


class ShopifyProductsSyncer(ShopifyResourceSyncer):
    resource: ClassVar[str] = "products"
    response_key = "products"
    path = admin_path("products")

    def source_record_id(self, raw: dict[str, Any]) -> str:
        return shopify_id(raw)

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        variants = raw.get("variants") or []
        first_variant = variants[0] if variants else {}
        return {
            "title": raw.get("title") or "Untitled product",
            "sku": first_variant.get("sku"),
            "price_paise": money_to_paise(first_variant.get("price")),
            "currency": "INR",
            "weight_grams": first_variant.get("grams"),
            "extras": {
                "handle": raw.get("handle"),
                "vendor": raw.get("vendor"),
                "product_type": raw.get("product_type"),
                "variants": variants,
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
            table="products",
            merchant_id=self.connector.connection.merchant_id,
            source=self.connector.source,
            source_record_id=normalized.pop("source_record_id"),
            raw_record_id=raw_record_id,
            sync_run_id=sync_run_id,
            values=normalized,
        )

