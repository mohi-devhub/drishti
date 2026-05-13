from __future__ import annotations

from drishti.agents.base import Finding
from drishti.chat.citation_validator import validate_citations
from drishti.chat.tools.registry import CitedAggregate, ToolResult


def narrate(finding: Finding) -> tuple[str | None, str, dict]:
    tool_result = finding.tool_result
    if tool_result is None:
        return None, "failed", {}

    savings_low = _aggregate(tool_result, "estimated_saving_low_inr")
    savings_high = _aggregate(tool_result, "estimated_saving_high_inr")
    evidence_count = _aggregate(tool_result, "evidence_count")
    if not savings_low or not savings_high or not evidence_count:
        return None, "failed", {}

    narrative = (
        f"{finding.finding_type} has "
        f"<cite {evidence_count.agg_id}>{int(evidence_count.value)}</cite> cited evidence rows "
        f"and estimated savings of <cite {savings_low.agg_id}>₹{int(savings_low.value) // 100:,}</cite>"
        f"-<cite {savings_high.agg_id}>₹{int(savings_high.value) // 100:,}</cite>."
    )
    validation = validate_citations(narrative, [tool_result], auto_attach=False)
    if not validation.passed:
        return None, "degraded", {"failures": [failure.__dict__ for failure in validation.failures]}
    return validation.text, "validated", {"tool_result": tool_result.model_dump()}


def _aggregate(tool_result: ToolResult, label: str) -> CitedAggregate | None:
    for aggregate in tool_result.aggregates:
        if aggregate.label == label:
            return aggregate
    return None
