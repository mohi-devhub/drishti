from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from drishti.db.repositories import source_records


Cursor = dict[str, Any]
RawRecord = dict[str, Any]
NormalizedRecord = dict[str, Any]


@dataclass(frozen=True)
class Page:
    records: list[RawRecord]
    next_cursor: Cursor | None = None
    has_more: bool = False
    endpoint: str = ""


@dataclass(frozen=True)
class SyncLoopResult:
    raw_record_ids: list[UUID]
    cursor_after: Cursor | None
    records_fetched: int
    api_calls: int


class ResourceSyncer(ABC):
    resource: ClassVar[str]

    def __init__(self, connector) -> None:
        self.connector = connector

    @abstractmethod
    async def fetch_page(self, cursor: Cursor | None) -> Page: ...

    def cursor_from(self, page: Page) -> Cursor | None:
        return page.next_cursor

    @abstractmethod
    def source_record_id(self, raw: RawRecord) -> str: ...

    @abstractmethod
    def normalize(self, raw: RawRecord) -> NormalizedRecord: ...

    @abstractmethod
    async def upsert(
        self,
        session: AsyncSession,
        normalized: NormalizedRecord,
        *,
        raw_record_id: UUID,
        sync_run_id: UUID,
    ) -> UUID: ...

    async def sync_raw_page_loop(
        self,
        session: AsyncSession,
        *,
        sync_run_id: UUID,
        cursor: Cursor | None,
        max_pages: int = 25,
    ) -> SyncLoopResult:
        raw_record_ids: list[UUID] = []
        current_cursor = cursor
        page_count = 0
        api_calls = 0

        while True:
            page = await self.fetch_page(current_cursor)
            api_calls += 1
            page_count += 1
            fetched_at = datetime.now(UTC)
            for raw in page.records:
                raw_record_ids.append(
                    await source_records.insert_raw(
                        session,
                        merchant_id=self.connector.connection.merchant_id,
                        source=self.connector.source,
                        resource=self.resource,
                        source_record_id=self.source_record_id(raw),
                        endpoint=page.endpoint,
                        payload=raw,
                        fetched_at=fetched_at,
                        sync_run_id=sync_run_id,
                    )
                )
            current_cursor = self.cursor_from(page)
            if not page.has_more or current_cursor is None or page_count >= max_pages:
                break

        return SyncLoopResult(
            raw_record_ids=raw_record_ids,
            cursor_after=current_cursor,
            records_fetched=len(raw_record_ids),
            api_calls=api_calls,
        )


async def upsert_domain_row(
    session: AsyncSession,
    *,
    table: str,
    merchant_id: UUID,
    source: str,
    source_record_id: str,
    raw_record_id: UUID,
    sync_run_id: UUID,
    values: dict[str, Any],
) -> UUID:
    columns = [
        "merchant_id",
        "source",
        "source_record_id",
        "raw_record_id",
        "sync_run_id",
        *values.keys(),
        "synced_at",
        "created_at",
        "updated_at",
    ]
    insert_names = ", ".join(columns)
    placeholders = ", ".join(_placeholder(column) for column in columns)
    update_columns = [
        "raw_record_id",
        "sync_run_id",
        *values.keys(),
        "synced_at",
        "updated_at",
    ]
    updates = ", ".join(f"{column} = EXCLUDED.{column}" for column in update_columns)
    params = {
        "merchant_id": str(merchant_id),
        "source": source,
        "source_record_id": source_record_id,
        "raw_record_id": str(raw_record_id),
        "sync_run_id": str(sync_run_id),
        **{key: _serialize_param(value) for key, value in values.items()},
        "synced_at": datetime.now(UTC),
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    result = await session.execute(
        text(
            f"""
            INSERT INTO {table} ({insert_names})
            VALUES ({placeholders})
            ON CONFLICT (merchant_id, source, source_record_id)
            DO UPDATE SET {updates}
            RETURNING id
            """
        ),
        params,
    )
    return result.scalar_one()


def _placeholder(column: str) -> str:
    if column == "extras":
        return f"CAST(:{column} AS jsonb)"
    return f":{column}"


def _serialize_param(value: Any) -> Any:
    if isinstance(value, dict | list):
        return json.dumps(value, sort_keys=True, default=str)
    return value
