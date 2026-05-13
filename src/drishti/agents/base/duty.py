from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from drishti.chat.tools.registry import ToolResult


@dataclass(frozen=True)
class Finding:
    duty: str
    finding_type: str
    severity: str
    confidence: float
    evidence_row_ids: list[str]
    estimated_saving_inr_low: int | None
    estimated_saving_inr_high: int | None
    metadata: dict[str, Any] = field(default_factory=dict)
    proposed_action: dict[str, Any] = field(default_factory=dict)
    tool_result: ToolResult | None = None


class Duty(Protocol):
    name: str

    async def detect(self, session: AsyncSession) -> list[Finding]: ...
