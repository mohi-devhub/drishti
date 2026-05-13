from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from drishti.agents.base import Agent
from drishti.agents.rto_shipping_margin.duties import (
    CodRtoRiskDuty,
    CourierMarginDriftDuty,
    DelayedPrepaidDuty,
    RefundShippingMismatchDuty,
)
from drishti.agents.rto_shipping_margin.narrator import narrate
from drishti.config import Settings
from drishti.db.repositories import agent_runs


def build_agent() -> Agent:
    return Agent(
        duties=[
            CodRtoRiskDuty(),
            CourierMarginDriftDuty(),
            DelayedPrepaidDuty(),
            RefundShippingMismatchDuty(),
        ]
    )


async def run_worker(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    trigger: str = "manual",
    settings: Settings | None = None,
) -> dict:
    snapshot = await input_snapshot(session, merchant_id=merchant_id)
    run_id = await agent_runs.create(
        session,
        merchant_id=merchant_id,
        trigger=trigger,
        input_snapshot=snapshot,
    )
    result = await build_agent().detect(session)
    finding_ids = []
    for finding in result.findings:
        narrative, narrative_status, citations = await narrate(finding, settings=settings)
        finding_ids.append(
            await agent_runs.insert_finding(
                session,
                merchant_id=merchant_id,
                run_id=run_id,
                duty=finding.duty,
                finding_type=finding.finding_type,
                severity=finding.severity,
                confidence=finding.confidence,
                evidence_row_ids=finding.evidence_row_ids,
                estimated_saving_inr_low=finding.estimated_saving_inr_low,
                estimated_saving_inr_high=finding.estimated_saving_inr_high,
                narrative=narrative,
                narrative_status=narrative_status,
                proposed_action=finding.proposed_action,
                citations=citations,
            )
        )
    status = "partial" if result.errors or result.duties_skipped else "completed"
    await agent_runs.finish(
        session,
        merchant_id=merchant_id,
        run_id=run_id,
        status=status,
        duties_run=result.duties_run,
        duties_skipped=result.duties_skipped,
        findings_count=len(finding_ids),
        errors=result.errors,
    )
    return {
        "run_id": str(run_id),
        "status": status,
        "findings_count": len(finding_ids),
        "finding_ids": [str(finding_id) for finding_id in finding_ids],
        "duties_run": result.duties_run,
        "errors": result.errors,
    }


async def input_snapshot(session: AsyncSession, *, merchant_id: UUID) -> dict:
    result = await session.execute(
        text(
            """
            SELECT 'orders' AS name, COUNT(*) AS row_count, MAX(synced_at) AS last_synced_at
            FROM orders WHERE merchant_id = :merchant_id
            UNION ALL
            SELECT 'shipments', COUNT(*), MAX(synced_at)
            FROM shipments WHERE merchant_id = :merchant_id
            UNION ALL
            SELECT 'payments', COUNT(*), MAX(synced_at)
            FROM payments WHERE merchant_id = :merchant_id
            UNION ALL
            SELECT 'order_links', COUNT(*), MAX(updated_at)
            FROM order_links WHERE merchant_id = :merchant_id
            """
        ),
        {"merchant_id": str(merchant_id)},
    )
    return {
        row["name"]: {
            "row_count": int(row["row_count"] or 0),
            "last_synced_at": row["last_synced_at"].isoformat() if row["last_synced_at"] else None,
        }
        for row in result.mappings().all()
    }
