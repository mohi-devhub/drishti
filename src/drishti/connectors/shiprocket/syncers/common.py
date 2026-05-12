from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from drishti.connectors.base.resource_syncer import Cursor, Page, ResourceSyncer


class ShiprocketListSyncer(ResourceSyncer):
    response_key: str
    path: str

    async def fetch_page(self, cursor: Cursor | None) -> Page:
        params = dict(cursor or {})
        params.setdefault("page", 1)
        response = await self.connector.request("GET", self.path, params=params)
        payload = response.json() or {}
        records = payload.get(self.response_key, payload.get("data", []))
        if isinstance(records, dict):
            records = records.get(self.response_key, records.get("data", []))
        page = int(params.get("page") or 1)
        total_pages = int(payload.get("total_pages") or payload.get("last_page") or page)
        next_cursor = {**params, "page": page + 1} if page < total_pages else None
        return Page(
            records=records,
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
            endpoint=f"GET {self.path}",
        )


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def money_to_paise(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int((Decimal(str(value)) * 100).quantize(Decimal("1")))
    except (InvalidOperation, ValueError):
        return None


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def shipment_status(raw: dict[str, Any]) -> str:
    source_status = str(first_present(raw.get("status"), raw.get("current_status")) or "").lower()
    if "rto delivered" in source_status:
        return "rto_delivered"
    if "rto" in source_status and "initiated" in source_status:
        return "rto_initiated"
    if "rto" in source_status:
        return "rto_in_transit"
    if "delivered" in source_status:
        return "delivered"
    if "out for delivery" in source_status:
        return "out_for_delivery"
    if "picked" in source_status:
        return "picked_up"
    if "transit" in source_status or "shipped" in source_status:
        return "in_transit"
    if "cancel" in source_status:
        return "cancelled"
    if "lost" in source_status:
        return "lost"
    if "undelivered" in source_status:
        return "undelivered"
    return "created"
