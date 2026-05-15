from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from drishti.connectors.base import ConnectorConnection


async def get_active_by_source(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    source: str,
) -> ConnectorConnection | None:
    result = await session.execute(
        text(
            """
            SELECT id, merchant_id, source, auth_payload, cursors
            FROM connections
            WHERE merchant_id = :merchant_id
              AND source = :source
              AND status = 'active'
            """
        ),
        {"merchant_id": str(merchant_id), "source": source},
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None
    return ConnectorConnection(
        id=row["id"],
        merchant_id=row["merchant_id"],
        source=row["source"],
        auth_payload=dict(row["auth_payload"] or {}),
        cursors=dict(row["cursors"] or {}),
    )


async def get_active_shopify_by_shop_domain(
    session: AsyncSession,
    *,
    shop_domain: str,
) -> ConnectorConnection | None:
    normalized = _normalize_shop_domain(shop_domain)
    result = await session.execute(
        text(
            """
            SELECT id, merchant_id, source, auth_payload, cursors
            FROM resolve_shopify_connection_for_webhook(:shop_domain)
            """
        ),
        {"shop_domain": normalized},
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None
    return ConnectorConnection(
        id=row["id"],
        merchant_id=row["merchant_id"],
        source=row["source"],
        auth_payload=dict(row["auth_payload"] or {}),
        cursors=dict(row["cursors"] or {}),
    )


async def update_resource_cursor(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    connection_id: UUID,
    resource: str,
    cursor: dict[str, Any] | None,
) -> None:
    await session.execute(
        text(
            """
            UPDATE connections
            SET cursors = jsonb_set(
                    cursors,
                    ARRAY[:resource],
                    CAST(:cursor AS jsonb),
                    true
                ),
                last_synced_at = now(),
                updated_at = now()
            WHERE merchant_id = :merchant_id
              AND id = :connection_id
            """
        ),
        {
            "merchant_id": str(merchant_id),
            "connection_id": str(connection_id),
            "resource": resource,
            "cursor": json.dumps(cursor or {}, sort_keys=True, default=str),
        },
    )


def _normalize_shop_domain(shop_domain: str) -> str:
    return shop_domain.removeprefix("https://").removeprefix("http://").strip().strip("/").lower()
