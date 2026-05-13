from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from drishti.agents.base import Finding
from drishti.agents.rto_shipping_margin.duties.common import finding_tool_result, severity_for


class CourierMarginDriftDuty:
    name = "courier_margin_drift"

    async def detect(self, session: AsyncSession) -> list[Finding]:
        result = await session.execute(
            text(
                """
                WITH stats AS (
                  SELECT courier_id, courier_name,
                         LEFT(pickup_pincode, 3) || '_' || LEFT(delivery_pincode, 3) AS route,
                         COUNT(*) AS shipment_count,
                         AVG(freight_paise::numeric / NULLIF(weight_grams, 0)) AS freight_per_g,
                         AVG(weight_grams) AS avg_weight_g,
                         ARRAY_AGG('shipment:' || id::text) AS evidence_row_ids
                  FROM shipments
                  WHERE merchant_id = current_setting('app.current_merchant_id')::uuid
                    AND picked_up_at >= now() - interval '30 days'
                    AND weight_grams > 0
                    AND freight_paise IS NOT NULL
                  GROUP BY courier_id, courier_name, route
                  HAVING COUNT(*) >= 5
                ),
                baseline AS (
                  SELECT route, MIN(freight_per_g) AS best_freight_per_g
                  FROM stats
                  GROUP BY route
                  HAVING COUNT(DISTINCT courier_id) >= 2
                )
                SELECT s.*, b.best_freight_per_g,
                       GREATEST(s.freight_per_g - b.best_freight_per_g, 0) AS premium_per_g
                FROM stats s
                JOIN baseline b USING (route)
                WHERE s.freight_per_g >= b.best_freight_per_g * 1.25
                """
            )
        )
        findings = []
        for row in result.mappings().all():
            premium_paise = float(row["premium_per_g"] or 0) * float(row["avg_weight_g"] or 0) * int(row["shipment_count"])
            low = int(premium_paise * 0.75 / 100)
            high = int(premium_paise / 100)
            evidence = list(row["evidence_row_ids"] or [])
            tool_result = finding_tool_result(
                tool_name=self.name,
                row_id=f"courier_route:{row['courier_id']}:{row['route']}",
                values=dict(row),
                evidence_row_ids=evidence,
                estimated_low_inr=low,
                estimated_high_inr=high,
            )
            findings.append(
                Finding(
                    duty=self.name,
                    finding_type="courier_margin_drift_route",
                    severity=severity_for(high),
                    confidence=min(1.0, len(evidence) / 20),
                    evidence_row_ids=evidence,
                    estimated_saving_inr_low=low,
                    estimated_saving_inr_high=high,
                    metadata=dict(row),
                    proposed_action={
                        "action_type": "switch_default_courier_for_route",
                        "parameters": {"route": row["route"], "courier_id": row["courier_id"]},
                    },
                    tool_result=tool_result,
                )
            )
        return findings
