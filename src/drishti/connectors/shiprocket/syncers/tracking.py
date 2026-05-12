from __future__ import annotations

import json
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from drishti.connectors.base.resource_syncer import Cursor, Page, ResourceSyncer
from drishti.connectors.shiprocket.syncers.common import first_present, parse_datetime, shipment_status


class ShiprocketTrackingSyncer(ResourceSyncer):
    resource: ClassVar[str] = "tracking"

    async def fetch_page(self, cursor: Cursor | None) -> Page:
        awb = (cursor or {}).get("awb_code")
        if not awb:
            raise ValueError("Shiprocket tracking cursor.awb_code is required")
        path = f"/v1/external/courier/track/awb/{awb}"
        response = await self.connector.request("GET", path)
        payload = response.json() or {}
        records = payload.get("tracking_data", {}).get("shipment_track_activities")
        if records is None:
            records = payload.get("events", payload.get("tracking_events", []))
        for record in records:
            record.setdefault("awb_code", awb)
        return Page(records=records, endpoint=f"GET {path}")

    def source_record_id(self, raw: dict[str, Any]) -> str:
        return ":".join(
            [
                str(first_present(raw.get("awb_code"), raw.get("awb"))),
                str(first_present(raw.get("date"), raw.get("event_at"), raw.get("activity_date"))),
                str(first_present(raw.get("status"), raw.get("activity"))),
            ]
        )

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "awb_code": first_present(raw.get("awb_code"), raw.get("awb")),
            "event_status": shipment_status(raw),
            "event_message": first_present(raw.get("activity"), raw.get("message"), raw.get("status")),
            "location": raw.get("location"),
            "event_at": parse_datetime(first_present(raw.get("date"), raw.get("event_at"), raw.get("activity_date"))),
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
        result = await session.execute(
            text(
                """
                SELECT id
                FROM shipments
                WHERE merchant_id = :merchant_id
                  AND awb_code = :awb_code
                """
            ),
            {
                "merchant_id": str(self.connector.connection.merchant_id),
                "awb_code": normalized["awb_code"],
            },
        )
        shipment_id = result.scalar_one()
        inserted = await session.execute(
            text(
                """
                INSERT INTO tracking_events (
                    merchant_id, shipment_id, raw_record_id, sync_run_id,
                    event_status, event_message, location, event_at, created_at
                )
                VALUES (
                    :merchant_id, :shipment_id, :raw_record_id, :sync_run_id,
                    :event_status, :event_message, :location, :event_at, now()
                )
                RETURNING id
                """
            ),
            {
                "merchant_id": str(self.connector.connection.merchant_id),
                "shipment_id": str(shipment_id),
                "raw_record_id": str(raw_record_id),
                "sync_run_id": str(sync_run_id),
                "event_status": normalized["event_status"],
                "event_message": normalized.get("event_message"),
                "location": normalized.get("location"),
                "event_at": normalized["event_at"],
                "extras": json.dumps(normalized.get("extras", {}), sort_keys=True, default=str),
            },
        )
        return inserted.scalar_one()
