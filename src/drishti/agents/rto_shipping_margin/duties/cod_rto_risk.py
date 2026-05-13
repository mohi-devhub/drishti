from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from drishti.agents.base import Finding
from drishti.agents.rto_shipping_margin.duties.common import finding_tool_result, severity_for


class CodRtoRiskDuty:
    name = "cod_rto_risk"

    async def detect(self, session: AsyncSession) -> list[Finding]:
        result = await session.execute(
            text(
                """
                WITH cod_orders AS (
                  SELECT o.id AS order_id, s.id AS shipment_id,
                         LEFT(COALESCE(o.shipping_pincode, s.delivery_pincode), 4) AS pincode_cluster,
                         s.status AS shipment_status, COALESCE(s.freight_paise, 0) AS freight_paise
                  FROM orders o
                  JOIN order_links ol ON ol.order_id = o.id
                    AND ol.merchant_id = o.merchant_id
                    AND ol.confidence >= 0.8
                  JOIN shipments s ON s.id = ol.shipment_id AND s.merchant_id = ol.merchant_id
                  WHERE o.merchant_id = current_setting('app.current_merchant_id')::uuid
                    AND o.payment_method = 'cod'
                    AND o.placed_at >= now() - interval '30 days'
                    AND o.total_paise < 50000
                )
                SELECT pincode_cluster,
                       COUNT(*) AS order_count,
                       COUNT(*) FILTER (WHERE shipment_status LIKE 'rto%') AS rto_count,
                       COALESCE(SUM(freight_paise) FILTER (WHERE shipment_status LIKE 'rto%'), 0) AS freight_loss_paise,
                       ARRAY_AGG('order:' || order_id::text) ||
                       ARRAY_AGG('shipment:' || shipment_id::text) AS evidence_row_ids
                FROM cod_orders
                GROUP BY pincode_cluster
                HAVING COUNT(*) >= 5
                   AND COUNT(*) FILTER (WHERE shipment_status LIKE 'rto%')::numeric / COUNT(*) >= 0.40
                   AND COALESCE(SUM(freight_paise) FILTER (WHERE shipment_status LIKE 'rto%'), 0) >= 100000
                """
            )
        )
        findings = []
        for row in result.mappings().all():
            freight_loss_paise = int(row["freight_loss_paise"] or 0)
            low = freight_loss_paise * 14 // 1000
            high = freight_loss_paise * 16 // 1000
            evidence = list(row["evidence_row_ids"] or [])
            tool_result = finding_tool_result(
                tool_name=self.name,
                row_id=f"cod_rto:{row['pincode_cluster']}",
                values=dict(row),
                evidence_row_ids=evidence,
                estimated_low_inr=low,
                estimated_high_inr=high,
            )
            findings.append(
                Finding(
                    duty=self.name,
                    finding_type="cod_rto_pincode_cluster",
                    severity=severity_for(high),
                    confidence=min(1.0, len(evidence) / 20),
                    evidence_row_ids=evidence,
                    estimated_saving_inr_low=low,
                    estimated_saving_inr_high=high,
                    metadata=dict(row),
                    proposed_action={
                        "action_type": "require_prepaid_for_segment",
                        "parameters": {"pincode_prefix": row["pincode_cluster"], "payment_method": "cod"},
                    },
                    tool_result=tool_result,
                )
            )
        return findings
