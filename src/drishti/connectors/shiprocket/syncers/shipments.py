from __future__ import annotations

from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from drishti.connectors.base.resource_syncer import upsert_domain_row
from drishti.connectors.shiprocket.syncers.common import (
    ShiprocketListSyncer,
    first_present,
    money_to_paise,
    parse_datetime,
    shipment_status,
)
from drishti.db.repositories import order_links


class ShiprocketShipmentsSyncer(ShiprocketListSyncer):
    resource: ClassVar[str] = "shipments"
    response_key = "shipments"
    path = "/v1/external/shipments"

    def source_record_id(self, raw: dict[str, Any]) -> str:
        return str(first_present(raw.get("id"), raw.get("shipment_id"), raw.get("awb_code")))

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "awb_code": first_present(raw.get("awb_code"), raw.get("awb")),
            "courier_id": str(first_present(raw.get("courier_id"), raw.get("courier_company_id")) or ""),
            "courier_name": first_present(raw.get("courier_name"), raw.get("courier_company")),
            "status": shipment_status(raw),
            "freight_paise": money_to_paise(first_present(raw.get("freight_charges"), raw.get("freight"))),
            "weight_grams": _weight_grams(raw),
            "pickup_pincode": first_present(raw.get("pickup_pincode"), raw.get("pickup_postcode")),
            "delivery_pincode": first_present(raw.get("delivery_pincode"), raw.get("customer_pincode")),
            "picked_up_at": parse_datetime(raw.get("picked_up_at")),
            "delivered_at": parse_datetime(raw.get("delivered_at")),
            "rto_initiated_at": parse_datetime(raw.get("rto_initiated_at")),
            "expected_delivery_at": parse_datetime(raw.get("expected_delivery_at")),
            "extras": {
                "order_id": first_present(raw.get("order_id"), raw.get("channel_order_id")),
                "shipment_id": raw.get("shipment_id"),
                "raw_status": first_present(raw.get("status"), raw.get("current_status")),
            },
        }

    def follow_up_sync_jobs(self, raw: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        awb_code = first_present(raw.get("awb_code"), raw.get("awb"))
        status = shipment_status(raw)
        if not awb_code or status in {"delivered", "rto_delivered", "cancelled", "lost"}:
            return []
        return [("tracking", {"awb_code": str(awb_code)})]

    async def upsert(
        self,
        session: AsyncSession,
        normalized: dict[str, Any],
        *,
        raw_record_id: UUID,
        sync_run_id: UUID,
    ) -> UUID:
        source_record_id = normalized.pop("source_record_id")
        shipment_id = await upsert_domain_row(
            session,
            table="shipments",
            merchant_id=self.connector.connection.merchant_id,
            source=self.connector.source,
            source_record_id=source_record_id,
            raw_record_id=raw_record_id,
            sync_run_id=sync_run_id,
            values=normalized,
        )
        order_ref = normalized.get("extras", {}).get("order_id")
        if order_ref:
            await order_links.link_order_to_shipment(
                session,
                merchant_id=self.connector.connection.merchant_id,
                order_reference=str(order_ref),
                shipment_id=shipment_id,
            )
        return shipment_id


def _weight_grams(raw: dict[str, Any]) -> int | None:
    value = first_present(raw.get("weight_grams"), raw.get("weight"))
    if value in (None, ""):
        return None
    number = float(value)
    return int(number if number > 30 else number * 1000)
