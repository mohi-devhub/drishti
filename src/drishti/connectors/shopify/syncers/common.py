from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import parse_qs, urlparse

from drishti.connectors.base.resource_syncer import Cursor, Page, ResourceSyncer
from drishti.connectors.shopify.connector import SHOPIFY_API_VERSION


class ShopifyResourceSyncer(ResourceSyncer):
    response_key: str
    path: str

    async def fetch_page(self, cursor: Cursor | None) -> Page:
        params = {"limit": 250}
        if self.resource == "orders":
            params["status"] = "any"
        if cursor and cursor.get("page_info"):
            params = {"limit": 250, "page_info": cursor["page_info"]}
        elif cursor and cursor.get("updated_at_min"):
            params["updated_at_min"] = cursor["updated_at_min"]

        response = await self.connector.request("GET", self.path, params=params)
        payload = response.json()
        records = payload.get(self.response_key, [])
        next_cursor = self._cursor_from_link(response.headers.get("link"))
        return Page(
            records=records,
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
            endpoint=f"GET {self.path}",
        )

    def _cursor_from_link(self, link_header: str | None) -> Cursor | None:
        if not link_header:
            return None
        for part in link_header.split(","):
            if 'rel="next"' not in part:
                continue
            match = re.search(r"<([^>]+)>", part)
            if not match:
                continue
            query = parse_qs(urlparse(match.group(1)).query)
            page_info = query.get("page_info", [None])[0]
            if page_info:
                return {"page_info": page_info}
        return None


def admin_path(resource: str) -> str:
    return f"/admin/api/{SHOPIFY_API_VERSION}/{resource}.json"


def money_to_paise(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int((Decimal(str(value)) * 100).quantize(Decimal("1")))
    except (InvalidOperation, ValueError):
        return None


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    normalized = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def shopify_id(raw: dict[str, Any]) -> str:
    return str(raw["id"])


def shipping_price_paise(raw: dict[str, Any]) -> int | None:
    price_set = raw.get("total_shipping_price_set", {})
    amount = price_set.get("shop_money", {}).get("amount")
    if amount is not None:
        return money_to_paise(amount)
    shipping_lines = raw.get("shipping_lines") or []
    total = sum(money_to_paise(line.get("price")) or 0 for line in shipping_lines)
    return total if shipping_lines else None


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None

