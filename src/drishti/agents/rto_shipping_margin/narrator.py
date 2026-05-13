from __future__ import annotations

from openai import AsyncOpenAI

from drishti.agents.base import Finding
from drishti.chat.citation_validator import validate_citations
from drishti.chat.tools.registry import CitedAggregate, ToolResult
from drishti.config import Settings


async def narrate(
    finding: Finding,
    *,
    settings: Settings | None = None,
) -> tuple[str | None, str, dict]:
    tool_result = finding.tool_result
    if tool_result is None:
        return None, "failed", {}

    narrative = None
    if settings and settings.openai_api_key:
        narrative = await _openai_narrative(finding, settings=settings)
    if narrative is None:
        narrative = _fallback_narrative(finding)

    validation = validate_citations(narrative, [tool_result], auto_attach=False)
    if not validation.passed:
        retry = _fallback_narrative(finding)
        validation = validate_citations(retry, [tool_result], auto_attach=False)
    if not validation.passed:
        return None, "degraded", {"failures": [failure.__dict__ for failure in validation.failures]}
    return validation.text, "validated", {"tool_result": tool_result.model_dump()}


def _fallback_narrative(finding: Finding) -> str:
    assert finding.tool_result is not None
    tool_result = finding.tool_result
    savings_low = _aggregate(tool_result, "estimated_saving_low_inr")
    savings_high = _aggregate(tool_result, "estimated_saving_high_inr")
    evidence_count = _aggregate(tool_result, "evidence_count")
    if not savings_low or not savings_high or not evidence_count:
        return "I do not have cited evidence for this finding."

    return (
        f"{finding.finding_type} has "
        f"<cite {evidence_count.agg_id}>{int(evidence_count.value)}</cite> cited evidence rows "
        f"and estimated savings of <cite {savings_low.agg_id}>₹{int(savings_low.value) // 100:,}</cite>"
        f"-<cite {savings_high.agg_id}>₹{int(savings_high.value) // 100:,}</cite>."
    )


async def _openai_narrative(finding: Finding, *, settings: Settings) -> str | None:
    if finding.tool_result is None:
        return None
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.responses.create(
        model=settings.openai_cheap_model,
        input=[
            {
                "role": "system",
                "content": (
                    "Write a concise merchant-facing finding narrative. "
                    "Every number must be copied from the supplied tool result and wrapped in "
                    "<cite id>number</cite>. Do not invent numbers."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Finding: {finding.finding_type}\n"
                    f"Metadata: {finding.metadata}\n"
                    f"Tool result: {finding.tool_result.model_dump()}\n"
                    "Write one sentence."
                ),
            },
        ],
    )
    return response.output_text or None


def _aggregate(tool_result: ToolResult, label: str) -> CitedAggregate | None:
    for aggregate in tool_result.aggregates:
        if aggregate.label == label:
            return aggregate
    return None
