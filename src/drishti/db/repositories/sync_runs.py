from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def create(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    source: str,
    resource: str,
    trigger: str,
    connection_id: UUID | None = None,
    cursor_before: dict[str, Any] | None = None,
    started_at: datetime | None = None,
) -> UUID:
    result = await session.execute(
        text(
            """
            INSERT INTO sync_runs (
                merchant_id,
                connection_id,
                source,
                resource,
                trigger,
                status,
                cursor_before,
                started_at
            )
            VALUES (
                :merchant_id,
                :connection_id,
                :source,
                :resource,
                :trigger,
                'running',
                CAST(:cursor_before AS jsonb),
                COALESCE(:started_at, now())
            )
            RETURNING id
            """
        ),
        {
            "merchant_id": str(merchant_id),
            "connection_id": str(connection_id) if connection_id else None,
            "source": source,
            "resource": resource,
            "trigger": trigger,
            "cursor_before": json.dumps(cursor_before or {}, sort_keys=True, default=str),
            "started_at": started_at,
        },
    )
    return result.scalar_one()


async def update_status(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    sync_run_id: UUID,
    status: str,
    finished_at: datetime | None = None,
    error: dict[str, Any] | None = None,
) -> None:
    await session.execute(
        text(
            """
            UPDATE sync_runs
            SET status = :status,
                finished_at = COALESCE(:finished_at, now()),
                error = CAST(:error AS jsonb)
            WHERE merchant_id = :merchant_id
              AND id = :sync_run_id
            """
        ),
        {
            "merchant_id": str(merchant_id),
            "sync_run_id": str(sync_run_id),
            "status": status,
            "finished_at": finished_at,
            "error": json.dumps(error, sort_keys=True, default=str) if error is not None else None,
        },
    )


async def record_metrics(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    sync_run_id: UUID,
    records_fetched: int | None = None,
    records_normalized: int | None = None,
    api_calls: int | None = None,
    api_throttle_events: int | None = None,
    queue_wait_ms: int | None = None,
    cursor_after: dict[str, Any] | None = None,
) -> None:
    await session.execute(
        text(
            """
            UPDATE sync_runs
            SET records_fetched = COALESCE(:records_fetched, records_fetched),
                records_normalized = COALESCE(:records_normalized, records_normalized),
                api_calls = COALESCE(:api_calls, api_calls),
                api_throttle_events = COALESCE(:api_throttle_events, api_throttle_events),
                queue_wait_ms = COALESCE(:queue_wait_ms, queue_wait_ms),
                cursor_after = COALESCE(CAST(:cursor_after AS jsonb), cursor_after)
            WHERE merchant_id = :merchant_id
              AND id = :sync_run_id
            """
        ),
        {
            "merchant_id": str(merchant_id),
            "sync_run_id": str(sync_run_id),
            "records_fetched": records_fetched,
            "records_normalized": records_normalized,
            "api_calls": api_calls,
            "api_throttle_events": api_throttle_events,
            "queue_wait_ms": queue_wait_ms,
            "cursor_after": (
                json.dumps(cursor_after, sort_keys=True, default=str)
                if cursor_after is not None
                else None
            ),
        },
    )
