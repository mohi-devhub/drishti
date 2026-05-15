from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def create(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    trigger: str,
    input_snapshot: dict[str, Any],
) -> UUID:
    result = await session.execute(
        text(
            """
            INSERT INTO agent_runs (
                merchant_id, agent_name, trigger, status, input_snapshot, started_at, created_at
            )
            VALUES (
                :merchant_id, 'rto_shipping_margin_worker', :trigger, 'running',
                CAST(:input_snapshot AS jsonb), now(), now()
            )
            RETURNING id
            """
        ),
        {
            "merchant_id": str(merchant_id),
            "trigger": trigger,
            "input_snapshot": json.dumps(input_snapshot, sort_keys=True, default=str),
        },
    )
    return result.scalar_one()


async def create_queued(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    trigger: str,
    input_snapshot: dict[str, Any],
) -> UUID:
    result = await session.execute(
        text(
            """
            INSERT INTO agent_runs (
                merchant_id, agent_name, trigger, status, input_snapshot, created_at
            )
            VALUES (
                :merchant_id, 'rto_shipping_margin_worker', :trigger, 'queued',
                CAST(:input_snapshot AS jsonb), now()
            )
            RETURNING id
            """
        ),
        {
            "merchant_id": str(merchant_id),
            "trigger": trigger,
            "input_snapshot": json.dumps(input_snapshot, sort_keys=True, default=str),
        },
    )
    return result.scalar_one()


async def mark_running(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    run_id: UUID,
) -> bool:
    result = await session.execute(
        text(
            """
            UPDATE agent_runs
            SET status = 'running',
                started_at = COALESCE(started_at, now())
            WHERE merchant_id = :merchant_id
              AND id = :run_id
              AND status = 'queued'
            RETURNING id
            """
        ),
        {"merchant_id": str(merchant_id), "run_id": str(run_id)},
    )
    return result.scalar_one_or_none() is not None


async def finish(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    run_id: UUID,
    status: str,
    duties_run: list[str],
    duties_skipped: list[dict[str, Any]],
    findings_count: int,
    errors: dict[str, Any] | None = None,
) -> None:
    await session.execute(
        text(
            """
            UPDATE agent_runs
            SET status = :status,
                duties_run = :duties_run,
                duties_skipped = CAST(:duties_skipped AS jsonb),
                findings_count = :findings_count,
                errors = CAST(:errors AS jsonb),
                finished_at = now()
            WHERE merchant_id = :merchant_id
              AND id = :run_id
            """
        ),
        {
            "merchant_id": str(merchant_id),
            "run_id": str(run_id),
            "status": status,
            "duties_run": duties_run,
            "duties_skipped": json.dumps(duties_skipped, sort_keys=True, default=str),
            "findings_count": findings_count,
            "errors": json.dumps(errors or {}, sort_keys=True, default=str),
        },
    )


async def insert_finding(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    run_id: UUID,
    duty: str,
    finding_type: str,
    severity: str,
    confidence: float,
    evidence_row_ids: list[str],
    estimated_saving_inr_low: int | None,
    estimated_saving_inr_high: int | None,
    narrative: str | None,
    narrative_status: str,
    proposed_action: dict[str, Any],
    citations: dict[str, Any],
) -> UUID:
    result = await session.execute(
        text(
            """
            INSERT INTO agent_findings (
                merchant_id, run_id, duty, finding_type, severity, confidence,
                evidence_row_ids, estimated_saving_inr_low, estimated_saving_inr_high,
                narrative, narrative_status, proposed_action, citations, created_at
            )
            VALUES (
                :merchant_id, :run_id, :duty, :finding_type, :severity, :confidence,
                :evidence_row_ids, :estimated_saving_inr_low, :estimated_saving_inr_high,
                :narrative, :narrative_status, CAST(:proposed_action AS jsonb),
                CAST(:citations AS jsonb), now()
            )
            RETURNING id
            """
        ),
        {
            "merchant_id": str(merchant_id),
            "run_id": str(run_id),
            "duty": duty,
            "finding_type": finding_type,
            "severity": severity,
            "confidence": confidence,
            "evidence_row_ids": evidence_row_ids,
            "estimated_saving_inr_low": estimated_saving_inr_low,
            "estimated_saving_inr_high": estimated_saving_inr_high,
            "narrative": narrative,
            "narrative_status": narrative_status,
            "proposed_action": json.dumps(proposed_action, sort_keys=True, default=str),
            "citations": json.dumps(citations, sort_keys=True, default=str),
        },
    )
    return result.scalar_one()


async def list_findings(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    limit: int = 50,
) -> list[dict[str, Any]]:
    result = await session.execute(
        text(
            """
            SELECT *
            FROM agent_findings
            WHERE merchant_id = :merchant_id
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        {"merchant_id": str(merchant_id), "limit": limit},
    )
    return [dict(row) for row in result.mappings().all()]


async def latest_run(
    session: AsyncSession,
    *,
    merchant_id: UUID,
) -> dict[str, Any] | None:
    result = await session.execute(
        text(
            """
            SELECT *
            FROM agent_runs
            WHERE merchant_id = :merchant_id
              AND agent_name = 'rto_shipping_margin_worker'
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {"merchant_id": str(merchant_id)},
    )
    row = result.mappings().one_or_none()
    return dict(row) if row else None


async def get_run(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    run_id: UUID,
) -> dict[str, Any] | None:
    result = await session.execute(
        text(
            """
            SELECT *
            FROM agent_runs
            WHERE merchant_id = :merchant_id
              AND id = :run_id
              AND agent_name = 'rto_shipping_margin_worker'
            """
        ),
        {"merchant_id": str(merchant_id), "run_id": str(run_id)},
    )
    row = result.mappings().one_or_none()
    return dict(row) if row else None


async def list_latest_findings(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    limit: int = 50,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    run = await latest_run(session, merchant_id=merchant_id)
    if run is None:
        return None, []
    result = await session.execute(
        text(
            """
            SELECT *
            FROM agent_findings
            WHERE merchant_id = :merchant_id
              AND run_id = :run_id
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        {"merchant_id": str(merchant_id), "run_id": str(run["id"]), "limit": limit},
    )
    return run, [dict(row) for row in result.mappings().all()]


async def get_finding(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    finding_id: UUID,
) -> dict[str, Any] | None:
    result = await session.execute(
        text(
            """
            SELECT *
            FROM agent_findings
            WHERE merchant_id = :merchant_id
              AND id = :finding_id
            """
        ),
        {"merchant_id": str(merchant_id), "finding_id": str(finding_id)},
    )
    row = result.mappings().one_or_none()
    return dict(row) if row else None
