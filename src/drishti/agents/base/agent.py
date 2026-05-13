from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from drishti.agents.base.duty import Duty, Finding


@dataclass
class AgentRunResult:
    findings: list[Finding]
    duties_run: list[str]
    duties_skipped: list[dict]
    errors: dict


class Agent:
    def __init__(self, duties: list[Duty]) -> None:
        self.duties = duties

    async def detect(self, session: AsyncSession) -> AgentRunResult:
        findings: list[Finding] = []
        duties_run: list[str] = []
        errors: dict = {}
        for duty in self.duties:
            try:
                duty_findings = await duty.detect(session)
                duties_run.append(duty.name)
                findings.extend(duty_findings)
            except Exception as exc:
                errors[duty.name] = {"type": type(exc).__name__, "message": str(exc)}
        return AgentRunResult(
            findings=findings,
            duties_run=duties_run,
            duties_skipped=[],
            errors=errors,
        )
