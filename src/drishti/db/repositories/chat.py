from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def create_session(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    clerk_user_id: str,
    title: str | None = None,
) -> UUID:
    result = await session.execute(
        text(
            """
            INSERT INTO chat_sessions (merchant_id, clerk_user_id, title, created_at, updated_at)
            VALUES (:merchant_id, :clerk_user_id, :title, now(), now())
            RETURNING id
            """
        ),
        {
            "merchant_id": str(merchant_id),
            "clerk_user_id": clerk_user_id,
            "title": title,
        },
    )
    return result.scalar_one()


async def insert_message(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    session_id: UUID,
    role: str,
    content: str,
    tool_call_id: UUID | None = None,
) -> UUID:
    result = await session.execute(
        text(
            """
            INSERT INTO chat_messages (
                merchant_id, session_id, role, content, tool_call_id, created_at
            )
            VALUES (
                :merchant_id, :session_id, :role, :content, :tool_call_id, now()
            )
            RETURNING id
            """
        ),
        {
            "merchant_id": str(merchant_id),
            "session_id": str(session_id),
            "role": role,
            "content": content,
            "tool_call_id": str(tool_call_id) if tool_call_id else None,
        },
    )
    await session.execute(
        text(
            """
            UPDATE chat_sessions
            SET updated_at = now()
            WHERE merchant_id = :merchant_id
              AND id = :session_id
            """
        ),
        {"merchant_id": str(merchant_id), "session_id": str(session_id)},
    )
    return result.scalar_one()


async def list_sessions(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    clerk_user_id: str | None = None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    result = await session.execute(
        text(
            """
            SELECT cs.id, cs.title, cs.clerk_user_id, cs.created_at, cs.updated_at,
                   COUNT(cm.id) AS message_count,
                   MAX(cm.content) FILTER (WHERE cm.created_at = latest.latest_message_at) AS latest_message
            FROM chat_sessions cs
            LEFT JOIN chat_messages cm
              ON cm.merchant_id = cs.merchant_id
             AND cm.session_id = cs.id
            LEFT JOIN LATERAL (
                SELECT MAX(created_at) AS latest_message_at
                FROM chat_messages
                WHERE merchant_id = cs.merchant_id
                  AND session_id = cs.id
            ) latest ON true
            WHERE cs.merchant_id = :merchant_id
              AND (CAST(:clerk_user_id AS text) IS NULL OR cs.clerk_user_id = CAST(:clerk_user_id AS text))
            GROUP BY cs.id, cs.title, cs.clerk_user_id, cs.created_at, cs.updated_at
            ORDER BY cs.updated_at DESC
            LIMIT :limit
            """
        ),
        {
            "merchant_id": str(merchant_id),
            "clerk_user_id": clerk_user_id,
            "limit": max(1, min(limit, 100)),
        },
    )
    return [dict(row) for row in result.mappings().all()]


async def delete_session(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    session_id: UUID,
    clerk_user_id: str | None = None,
) -> bool:
    params = {
        "merchant_id": str(merchant_id),
        "session_id": str(session_id),
        "clerk_user_id": clerk_user_id,
    }
    await session.execute(
        text(
            """
            DELETE FROM chat_messages
            WHERE merchant_id = :merchant_id
              AND session_id = :session_id
              AND session_id IN (
                  SELECT id FROM chat_sessions
                  WHERE merchant_id = :merchant_id
                    AND id = :session_id
                    AND (CAST(:clerk_user_id AS text) IS NULL OR clerk_user_id = CAST(:clerk_user_id AS text))
              )
            """
        ),
        params,
    )
    result = await session.execute(
        text(
            """
            DELETE FROM chat_sessions
            WHERE merchant_id = :merchant_id
              AND id = :session_id
              AND (CAST(:clerk_user_id AS text) IS NULL OR clerk_user_id = CAST(:clerk_user_id AS text))
            RETURNING id
            """
        ),
        params,
    )
    return result.scalar_one_or_none() is not None


async def list_messages(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    session_id: UUID,
) -> list[dict[str, Any]]:
    result = await session.execute(
        text(
            """
            SELECT id, role, content, tool_call_id, created_at
            FROM chat_messages
            WHERE merchant_id = :merchant_id
              AND session_id = :session_id
            ORDER BY created_at, id
            """
        ),
        {"merchant_id": str(merchant_id), "session_id": str(session_id)},
    )
    return [dict(row) for row in result.mappings().all()]


async def create_tool_call(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    caller: str,
    caller_id: UUID | None,
    tool_name: str,
    args: dict[str, Any],
    result: dict[str, Any] | None = None,
    result_id: str | None = None,
    validation_status: str = "pending",
    validation_failures: list[dict[str, Any]] | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> UUID:
    started = started_at or datetime.now(UTC)
    finished = finished_at or datetime.now(UTC)
    latency_ms = int((finished - started).total_seconds() * 1000)
    db_result = await session.execute(
        text(
            """
            INSERT INTO tool_calls (
                merchant_id, caller, caller_id, tool_name, args, result, result_id,
                validation_status, validation_failures, latency_ms, started_at, finished_at,
                created_at
            )
            VALUES (
                :merchant_id, :caller, :caller_id, :tool_name, CAST(:args AS jsonb),
                CAST(:result AS jsonb), :result_id, :validation_status,
                CAST(:validation_failures AS jsonb), :latency_ms, :started_at, :finished_at,
                now()
            )
            RETURNING id
            """
        ),
        {
            "merchant_id": str(merchant_id),
            "caller": caller,
            "caller_id": str(caller_id) if caller_id else None,
            "tool_name": tool_name,
            "args": json.dumps(args, sort_keys=True, default=str),
            "result": json.dumps(result, sort_keys=True, default=str) if result is not None else None,
            "result_id": result_id,
            "validation_status": validation_status,
            "validation_failures": json.dumps(validation_failures or [], sort_keys=True, default=str),
            "latency_ms": latency_ms,
            "started_at": started,
            "finished_at": finished,
        },
    )
    return db_result.scalar_one()
