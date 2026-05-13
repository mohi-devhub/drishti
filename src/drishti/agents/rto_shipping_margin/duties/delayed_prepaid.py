from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from drishti.agents.base import Finding
from drishti.agents.rto_shipping_margin.duties.common import finding_tool_result, severity_for


class DelayedPrepaidDuty:
    name = "delayed_prepaid"

    async def detect(self, session: AsyncSession) -> list[Finding]:
        result = await session.execute(
            text(
                """
                SELECT s.id AS shipment_id, o.id AS order_id, p.id AS payment_id,
                       s.awb_code, s.courier_name, s.expected_delivery_at, s.status,
                       o.total_paise,
                       EXTRACT(day FROM now() - s.expected_delivery_at)::int AS days_overdue
                FROM shipments s
                JOIN order_links ol ON ol.shipment_id = s.id
                  AND ol.merchant_id = s.merchant_id
                  AND ol.confidence >= 0.8
                JOIN orders o ON o.id = ol.order_id AND o.merchant_id = ol.merchant_id
                JOIN payments p ON p.id = ol.payment_id AND p.merchant_id = ol.merchant_id
                WHERE s.merchant_id = current_setting('app.current_merchant_id')::uuid
                  AND s.status NOT IN ('delivered', 'cancelled', 'rto_delivered', 'lost')
                  AND s.expected_delivery_at < now() - interval '2 days'
                  AND p.status = 'captured'
                  AND o.total_paise >= 100000
                ORDER BY days_overdue DESC
                LIMIT 50
                """
            )
        )
        findings = []
        for row in result.mappings().all():
            evidence = [
                f"shipment:{row['shipment_id']}",
                f"order:{row['order_id']}",
                f"payment:{row['payment_id']}",
            ]
            low = int(row["total_paise"] * 0.05 / 100)
            high = int(row["total_paise"] * 0.15 / 100)
            tool_result = finding_tool_result(
                tool_name=self.name,
                row_id=f"delayed_prepaid:{row['shipment_id']}",
                values=dict(row),
                evidence_row_ids=evidence,
                estimated_low_inr=low,
                estimated_high_inr=high,
            )
            findings.append(
                Finding(
                    duty=self.name,
                    finding_type="delayed_prepaid_shipment",
                    severity=severity_for(high),
                    confidence=0.9,
                    evidence_row_ids=evidence,
                    estimated_saving_inr_low=low,
                    estimated_saving_inr_high=high,
                    metadata=dict(row),
                    proposed_action={
                        "action_type": "escalate_to_courier_support",
                        "parameters": {"awb_code": row["awb_code"], "courier_name": row["courier_name"]},
                    },
                    tool_result=tool_result,
                )
            )
        return findings
