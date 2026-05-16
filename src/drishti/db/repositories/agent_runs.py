from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

FINDING_API_COLUMNS = """
    id,
    run_id,
    duty,
    finding_type,
    severity,
    lifecycle_status,
    fingerprint,
    confidence,
    evidence_row_ids,
    estimated_saving_inr_low,
    estimated_saving_inr_high,
    narrative,
    narrative_status,
    proposed_action,
    created_at
"""


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
    fingerprint = _finding_fingerprint(
        duty=duty,
        finding_type=finding_type,
        evidence_row_ids=evidence_row_ids,
        proposed_action=proposed_action,
    )
    result = await session.execute(
        text(
            """
            INSERT INTO agent_findings (
                merchant_id, run_id, duty, finding_type, severity, confidence,
                evidence_row_ids, estimated_saving_inr_low, estimated_saving_inr_high,
                narrative, narrative_status, proposed_action, citations, fingerprint, created_at
            )
            VALUES (
                :merchant_id, :run_id, :duty, :finding_type, :severity, :confidence,
                :evidence_row_ids, :estimated_saving_inr_low, :estimated_saving_inr_high,
                :narrative, :narrative_status, CAST(:proposed_action AS jsonb),
                CAST(:citations AS jsonb), :fingerprint, now()
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
            "fingerprint": fingerprint,
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
    severity: str | None = None,
    lifecycle_status: str | None = None,
    query: str | None = None,
    sort: str = "newest",
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    run = await latest_run(session, merchant_id=merchant_id)
    if run is None:
        return None, []
    order_by = {
        "newest": "created_at DESC",
        "savings": "estimated_saving_inr_high DESC NULLS LAST",
        "severity": "CASE severity WHEN 'high' THEN 3 WHEN 'medium' THEN 2 ELSE 1 END DESC, created_at DESC",
    }.get(sort, "created_at DESC")
    filters = ["merchant_id = :merchant_id", "run_id = :run_id"]
    params: dict[str, Any] = {
        "merchant_id": str(merchant_id),
        "run_id": str(run["id"]),
        "limit": limit,
    }
    if severity:
        filters.append("severity = :severity")
        params["severity"] = severity
    if lifecycle_status:
        filters.append("lifecycle_status = :lifecycle_status")
        params["lifecycle_status"] = lifecycle_status
    if query:
        filters.append(
            """
            (
              duty ILIKE '%' || :query || '%'
              OR finding_type ILIKE '%' || :query || '%'
              OR narrative ILIKE '%' || :query || '%'
            )
            """
        )
        params["query"] = query
    result = await session.execute(
        text(
            f"""
            SELECT {FINDING_API_COLUMNS}
            FROM agent_findings
            WHERE {" AND ".join(filters)}
            ORDER BY {order_by}
            LIMIT :limit
            """
        ),
        params,
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
            f"""
            SELECT {FINDING_API_COLUMNS}
            FROM agent_findings
            WHERE merchant_id = :merchant_id
              AND id = :finding_id
            """
        ),
        {"merchant_id": str(merchant_id), "finding_id": str(finding_id)},
    )
    row = result.mappings().one_or_none()
    return dict(row) if row else None


async def update_finding_lifecycle(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    finding_id: UUID,
    lifecycle_status: str,
) -> dict[str, Any] | None:
    result = await session.execute(
        text(
            """
            UPDATE agent_findings
            SET lifecycle_status = :lifecycle_status
            WHERE merchant_id = :merchant_id
              AND id = :finding_id
            RETURNING *
            """
        ),
        {
            "merchant_id": str(merchant_id),
            "finding_id": str(finding_id),
            "lifecycle_status": lifecycle_status,
        },
    )
    row = result.mappings().one_or_none()
    return dict(row) if row else None


async def cancel_run(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    run_id: UUID,
) -> bool:
    result = await session.execute(
        text(
            """
            UPDATE agent_runs
            SET status = 'cancelled',
                finished_at = now()
            WHERE merchant_id = :merchant_id
              AND id = :run_id
              AND status IN ('queued','running')
            RETURNING id
            """
        ),
        {"merchant_id": str(merchant_id), "run_id": str(run_id)},
    )
    return result.scalar_one_or_none() is not None


async def list_duty_configs(session: AsyncSession, *, merchant_id: UUID) -> list[dict[str, Any]]:
    result = await session.execute(
        text(
            """
            SELECT duty, enabled, config, updated_at
            FROM agent_duty_configs
            WHERE merchant_id = :merchant_id
            ORDER BY duty
            """
        ),
        {"merchant_id": str(merchant_id)},
    )
    return [dict(row) for row in result.mappings().all()]


async def upsert_duty_config(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    duty: str,
    enabled: bool,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = await session.execute(
        text(
            """
            INSERT INTO agent_duty_configs (merchant_id, duty, enabled, config, updated_at)
            VALUES (:merchant_id, :duty, :enabled, CAST(:config AS jsonb), now())
            ON CONFLICT (merchant_id, duty)
            DO UPDATE SET enabled = EXCLUDED.enabled,
                          config = EXCLUDED.config,
                          updated_at = now()
            RETURNING duty, enabled, config, updated_at
            """
        ),
        {
            "merchant_id": str(merchant_id),
            "duty": duty,
            "enabled": enabled,
            "config": json.dumps(config or {}, sort_keys=True, default=str),
        },
    )
    return dict(result.mappings().one())


def _finding_fingerprint(
    *,
    duty: str,
    finding_type: str,
    evidence_row_ids: list[str],
    proposed_action: dict[str, Any],
) -> str:
    payload = json.dumps(
        {
            "duty": duty,
            "finding_type": finding_type,
            "evidence_row_ids": sorted(evidence_row_ids),
            "action_type": proposed_action.get("action_type"),
            "parameters": proposed_action.get("parameters", {}),
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
