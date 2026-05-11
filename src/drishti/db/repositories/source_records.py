from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


async def insert_raw(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    source: str,
    resource: str,
    source_record_id: str,
    endpoint: str,
    payload: dict[str, Any],
    fetched_at: datetime,
    sync_run_id: UUID | None = None,
) -> UUID:
    digest = payload_hash(payload)
    result = await session.execute(
        text(
            """
            INSERT INTO source_records (
                merchant_id,
                sync_run_id,
                source,
                resource,
                source_record_id,
                endpoint,
                fetched_at,
                payload,
                payload_hash
            )
            VALUES (
                :merchant_id,
                :sync_run_id,
                :source,
                :resource,
                :source_record_id,
                :endpoint,
                :fetched_at,
                CAST(:payload AS jsonb),
                :payload_hash
            )
            ON CONFLICT (merchant_id, source, source_record_id, payload_hash) DO NOTHING
            RETURNING id
            """
        ),
        {
            "merchant_id": str(merchant_id),
            "sync_run_id": str(sync_run_id) if sync_run_id else None,
            "source": source,
            "resource": resource,
            "source_record_id": source_record_id,
            "endpoint": endpoint,
            "fetched_at": fetched_at,
            "payload": json.dumps(payload, sort_keys=True, default=str),
            "payload_hash": digest,
        },
    )
    inserted = result.scalar_one_or_none()
    if inserted is not None:
        return inserted

    existing = await session.execute(
        text(
            """
            SELECT id
            FROM source_records
            WHERE merchant_id = :merchant_id
              AND source = :source
              AND source_record_id = :source_record_id
              AND payload_hash = :payload_hash
            """
        ),
        {
            "merchant_id": str(merchant_id),
            "source": source,
            "source_record_id": source_record_id,
            "payload_hash": digest,
        },
    )
    return existing.scalar_one()


async def get_by_id(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    source_record_id: UUID,
) -> dict[str, Any] | None:
    result = await session.execute(
        text(
            """
            SELECT *
            FROM source_records
            WHERE merchant_id = :merchant_id
              AND id = :source_record_id
            """
        ),
        {"merchant_id": str(merchant_id), "source_record_id": str(source_record_id)},
    )
    row = result.mappings().one_or_none()
    return dict(row) if row else None


async def list_for_merchant(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    source: str | None = None,
    resource: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses = ["merchant_id = :merchant_id"]
    params: dict[str, Any] = {"merchant_id": str(merchant_id), "limit": limit}
    if source:
        clauses.append("source = :source")
        params["source"] = source
    if resource:
        clauses.append("resource = :resource")
        params["resource"] = resource

    result = await session.execute(
        text(
            f"""
            SELECT *
            FROM source_records
            WHERE {' AND '.join(clauses)}
            ORDER BY fetched_at DESC
            LIMIT :limit
            """
        ),
        params,
    )
    return [dict(row) for row in result.mappings().all()]
