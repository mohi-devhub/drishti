from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from drishti.connectors.base.resource_syncer import Cursor, Page, ResourceSyncer


class RazorpayListSyncer(ResourceSyncer):
    response_key = "items"
    path: str

    async def fetch_page(self, cursor: Cursor | None) -> Page:
        params = dict(cursor or {})
        now = datetime.now(UTC)
        params.setdefault("from", int((now - timedelta(days=7)).timestamp()))
        params.setdefault("to", int(now.timestamp()))
        params.setdefault("skip", 0)
        params.setdefault("count", 100)
        response = await self.connector.request("GET", self.path, params=params)
        payload = response.json() or {}
        records = payload.get(self.response_key, [])
        count = int(params["count"])
        skip = int(params["skip"])
        next_cursor = {**params, "skip": skip + count} if len(records) >= count else None
        return Page(
            records=records,
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
            endpoint=f"GET {self.path}",
        )


def epoch_to_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    return datetime.fromtimestamp(int(value), tz=UTC)


def paise(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None
