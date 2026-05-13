from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from drishti.agents.base import Finding
from drishti.agents.rto_shipping_margin.duties.common import finding_tool_result, severity_for


class RefundShippingMismatchDuty:
    name = "refund_shipping_mismatch"

    async def detect(self, session: AsyncSession) -> list[Finding]:
        result = await session.execute(
            text(
                """
                SELECT r.id AS refund_id, p.id AS payment_id, o.id AS order_id, s.id AS shipment_id,
                       r.amount_paise AS refund_amount_paise,
                       COALESCE(s.freight_paise, 0) AS freight_paise,
                       s.status AS shipment_status,
                       s.picked_up_at, r.processed_at AS refunded_at
                FROM refunds r
                JOIN payments p ON p.id = r.payment_id AND p.merchant_id = r.merchant_id
                JOIN order_links ol ON ol.payment_id = p.id
                  AND ol.merchant_id = p.merchant_id
                  AND ol.confidence >= 0.8
                JOIN orders o ON o.id = ol.order_id AND o.merchant_id = ol.merchant_id
                JOIN shipments s ON s.id = ol.shipment_id AND s.merchant_id = ol.merchant_id
                WHERE r.merchant_id = current_setting('app.current_merchant_id')::uuid
                  AND r.processed_at >= now() - interval '60 days'
                  AND s.picked_up_at IS NOT NULL
                  AND s.picked_up_at < r.processed_at
                  AND s.status NOT IN ('rto_delivered', 'rto_initiated', 'rto_in_transit')
                ORDER BY (r.amount_paise + COALESCE(s.freight_paise, 0)) DESC
                LIMIT 50
                """
            )
        )
        findings = []
        for row in result.mappings().all():
            evidence = [
                f"refund:{row['refund_id']}",
                f"payment:{row['payment_id']}",
                f"order:{row['order_id']}",
                f"shipment:{row['shipment_id']}",
            ]
            exposure_inr = int(((row["refund_amount_paise"] or 0) + (row["freight_paise"] or 0)) / 100)
            tool_result = finding_tool_result(
                tool_name=self.name,
                row_id=f"refund_shipping:{row['refund_id']}",
                values=dict(row),
                evidence_row_ids=evidence,
                estimated_low_inr=exposure_inr,
                estimated_high_inr=exposure_inr,
            )
            findings.append(
                Finding(
                    duty=self.name,
                    finding_type="refund_shipping_mismatch_order",
                    severity=severity_for(exposure_inr),
                    confidence=0.85,
                    evidence_row_ids=evidence,
                    estimated_saving_inr_low=exposure_inr,
                    estimated_saving_inr_high=exposure_inr,
                    metadata=dict(row),
                    proposed_action={
                        "action_type": "review_refund_policy_for_shipped_orders",
                        "parameters": {"refund_id": str(row["refund_id"])},
                    },
                    tool_result=tool_result,
                )
            )
        return findings
