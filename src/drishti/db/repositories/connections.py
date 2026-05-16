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


async def list_for_merchant(
    session: AsyncSession,
    *,
    merchant_id: UUID,
) -> list[dict[str, Any]]:
    result = await session.execute(
        text(
            """
            SELECT id, source, status, auth_payload, cursors, last_synced_at, created_at, updated_at
            FROM connections
            WHERE merchant_id = :merchant_id
            ORDER BY source
            """
        ),
        {"merchant_id": str(merchant_id)},
    )
    return [dict(row) for row in result.mappings().all()]


async def upsert_connection(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    source: str,
    auth_payload: dict[str, Any],
    status: str = "active",
) -> UUID:
    result = await session.execute(
        text(
            """
            INSERT INTO connections (
                merchant_id, source, status, auth_payload, cursors, created_at, updated_at
            )
            VALUES (
                :merchant_id, :source, :status, CAST(:auth_payload AS jsonb), '{}'::jsonb,
                now(), now()
            )
            ON CONFLICT (merchant_id, source)
            DO UPDATE SET status = EXCLUDED.status,
                          auth_payload = EXCLUDED.auth_payload,
                          updated_at = now()
            RETURNING id
            """
        ),
        {
            "merchant_id": str(merchant_id),
            "source": source,
            "status": status,
            "auth_payload": json.dumps(auth_payload, sort_keys=True, default=str),
        },
    )
    return result.scalar_one()


async def revoke(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    source: str,
) -> bool:
    result = await session.execute(
        text(
            """
            UPDATE connections
            SET status = 'revoked',
                updated_at = now()
            WHERE merchant_id = :merchant_id
              AND source = :source
              AND status != 'revoked'
            RETURNING id
            """
        ),
        {"merchant_id": str(merchant_id), "source": source},
    )
    return result.scalar_one_or_none() is not None


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


async def get_active_by_external_account(
    session: AsyncSession,
    *,
    source: str,
    account_key: str,
    account_id: str,
) -> ConnectorConnection | None:
    result = await session.execute(
        text(
            """
            SELECT id, merchant_id, source, auth_payload, cursors
            FROM connections
            WHERE source = :source
              AND status = 'active'
              AND auth_payload ->> :account_key = :account_id
            LIMIT 1
            """
        ),
        {"source": source, "account_key": account_key, "account_id": account_id},
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
