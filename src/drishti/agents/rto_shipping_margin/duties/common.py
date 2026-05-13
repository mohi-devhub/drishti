from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from drishti.chat.tools.registry import CitedAggregate, CitedRow, ToolResult


def finding_tool_result(
    *,
    tool_name: str,
    row_id: str,
    values: dict[str, Any],
    evidence_row_ids: list[str],
    estimated_low_inr: int,
    estimated_high_inr: int,
) -> ToolResult:
    return ToolResult(
        result_id=f"tr_{uuid4().hex[:12]}",
        tool_name=tool_name,
        args={},
        rows=[
            CitedRow(
                row_id=row_id,
                values=values,
                source="derived",
                source_record_id=row_id,
                raw_record_id="",
                fetched_from=tool_name,
                synced_at=datetime.now().isoformat(),
            )
        ],
        aggregates=[
            CitedAggregate(
                agg_id=f"agg_{uuid4().hex[:10]}",
                label="evidence_count",
                value=len(evidence_row_ids),
                unit="count",
                derived_from_row_ids=[row_id],
                formula="COUNT(evidence_row_ids)",
            ),
            CitedAggregate(
                agg_id=f"agg_{uuid4().hex[:10]}",
                label="estimated_saving_low_inr",
                value=estimated_low_inr * 100,
                unit="inr_paise",
                derived_from_row_ids=[row_id],
                formula="deterministic duty estimate low bound",
            ),
            CitedAggregate(
                agg_id=f"agg_{uuid4().hex[:10]}",
                label="estimated_saving_high_inr",
                value=estimated_high_inr * 100,
                unit="inr_paise",
                derived_from_row_ids=[row_id],
                formula="deterministic duty estimate high bound",
            ),
        ],
    )


def severity_for(high_inr: int) -> str:
    if high_inr >= 5000:
        return "high"
    if high_inr >= 1000:
        return "medium"
    return "low"
