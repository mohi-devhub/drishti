from __future__ import annotations

import json
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from drishti.connectors.base.resource_syncer import upsert_domain_row
from drishti.connectors.shopify.syncers.common import (
    ShopifyResourceSyncer,
    admin_path,
    first_present,
    money_to_paise,
    parse_datetime,
    shipping_price_paise,
    shopify_id,
)


class ShopifyOrdersSyncer(ShopifyResourceSyncer):
    resource: ClassVar[str] = "orders"
    response_key = "orders"
    path = admin_path("orders")

    def source_record_id(self, raw: dict[str, Any]) -> str:
        return shopify_id(raw)

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        shipping_address = raw.get("shipping_address") or {}
        line_items = raw.get("line_items") or []
        return {
            "placed_at": parse_datetime(raw.get("created_at")),
            "status": _order_status(raw),
            "payment_method": _payment_method(raw),
            "total_paise": money_to_paise(raw.get("total_price")) or 0,
            "subtotal_paise": money_to_paise(raw.get("subtotal_price")),
            "shipping_paise": shipping_price_paise(raw),
            "tax_paise": money_to_paise(raw.get("total_tax")),
            "discount_paise": money_to_paise(raw.get("total_discounts")),
            "currency": raw.get("currency") or "INR",
            "shipping_pincode": first_present(shipping_address.get("zip"), raw.get("shipping_zip")),
            "shipping_country": shipping_address.get("country_code") or "IN",
            "line_items_count": len(line_items),
            "extras": {
                "name": raw.get("name"),
                "order_number": raw.get("order_number"),
                "customer": raw.get("customer"),
                "line_items": line_items,
                "financial_status": raw.get("financial_status"),
                "fulfillment_status": raw.get("fulfillment_status"),
                "cancelled_at": raw.get("cancelled_at"),
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
        line_items = normalized.get("extras", {}).get("line_items", [])
        order_id = await upsert_domain_row(
            session,
            table="orders",
            merchant_id=self.connector.connection.merchant_id,
            source=self.connector.source,
            source_record_id=normalized.pop("source_record_id"),
            raw_record_id=raw_record_id,
            sync_run_id=sync_run_id,
            values=normalized,
        )
        await _replace_line_items(
            session,
            merchant_id=self.connector.connection.merchant_id,
            order_id=order_id,
            raw_record_id=raw_record_id,
            line_items=line_items,
        )
        return order_id


def _order_status(raw: dict[str, Any]) -> str:
    if raw.get("cancelled_at"):
        return "cancelled"
    financial_status = raw.get("financial_status")
    fulfillment_status = raw.get("fulfillment_status")
    if financial_status == "refunded":
        return "refunded"
    if financial_status == "partially_refunded":
        return "partially_refunded"
    if fulfillment_status == "fulfilled":
        return "fulfilled"
    if financial_status in {"paid", "authorized", "partially_paid"}:
        return "confirmed"
    return "placed"


def _payment_method(raw: dict[str, Any]) -> str:
    gateways = [str(value).lower() for value in raw.get("payment_gateway_names") or []]
    gateway = str(raw.get("gateway") or "").lower()
    joined = " ".join([gateway, *gateways])
    if "cod" in joined or "cash on delivery" in joined:
        return "cod"
    if joined.strip():
        return "prepaid"
    return "unknown"


async def _replace_line_items(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    order_id: UUID,
    raw_record_id: UUID,
    line_items: list[dict[str, Any]],
) -> None:
    await session.execute(
        text(
            """
            DELETE FROM order_line_items
            WHERE merchant_id = :merchant_id
              AND order_id = :order_id
            """
        ),
        {"merchant_id": str(merchant_id), "order_id": str(order_id)},
    )
    for item in line_items:
        quantity = int(item.get("quantity") or 0)
        unit_price = money_to_paise(item.get("price")) or 0
        await session.execute(
            text(
                """
                INSERT INTO order_line_items (
                    merchant_id,
                    order_id,
                    source_record_id,
                    raw_record_id,
                    quantity,
                    unit_price_paise,
                    total_paise,
                    extras
                )
                VALUES (
                    :merchant_id,
                    :order_id,
                    :source_record_id,
                    :raw_record_id,
                    :quantity,
                    :unit_price_paise,
                    :total_paise,
                    CAST(:extras AS jsonb)
                )
                """
            ),
            {
                "merchant_id": str(merchant_id),
                "order_id": str(order_id),
                "source_record_id": str(item.get("id")),
                "raw_record_id": str(raw_record_id),
                "quantity": quantity,
                "unit_price_paise": unit_price,
                "total_paise": quantity * unit_price,
                "extras": json.dumps(item, sort_keys=True, default=str),
            },
        )

