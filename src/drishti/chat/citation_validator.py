from __future__ import annotations

import re
from dataclasses import dataclass, field

from drishti.chat.tools.registry import ToolResult

CITE_RE = re.compile(r"<cite\s+([^>]+)>(.*?)</cite>", re.DOTALL)
NUMBER_RE = re.compile(r"(?:₹\s*)?\d(?:[\d,]*\d)?(?:\.\d+)?%?")


@dataclass(frozen=True)
class ValidationFailure:
    reason: str
    claim: str
    detail: str


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    text: str
    failures: list[ValidationFailure] = field(default_factory=list)
    auto_attached_count: int = 0


def validate_citations(text: str, tool_results: list[ToolResult], *, auto_attach: bool = True) -> ValidationResult:
    index = CitationIndex(tool_results)
    working_text = text
    auto_attached = 0
    if auto_attach:
        working_text, auto_attached = _auto_attach(working_text, index)

    failures: list[ValidationFailure] = []
    cited_ranges = [match.span() for match in CITE_RE.finditer(working_text)]
    for match in NUMBER_RE.finditer(working_text):
        if not _inside_any(match.span(), cited_ranges) and not _is_whitelisted_number(match.group(0), working_text, match.span()):
            failures.append(ValidationFailure("uncited", match.group(0), "numeric token is outside a cite tag"))

    for match in CITE_RE.finditer(working_text):
        ids = [item.strip() for item in match.group(1).split(",") if item.strip()]
        displayed = match.group(2)
        numeric = _parse_display_number(displayed)
        if numeric is None:
            failures.append(ValidationFailure("parse", displayed, "cited content does not contain a number"))
            continue
        if not ids:
            failures.append(ValidationFailure("bad_cite", displayed, "cite tag has no IDs"))
            continue
        for cite_id in ids:
            expected = index.value_for(cite_id)
            if expected is None:
                failures.append(ValidationFailure("bad_cite", cite_id, "cited ID does not exist in this turn"))
                continue
            if not _matches(expected, numeric, displayed):
                failures.append(
                    ValidationFailure(
                        "bad_value",
                        displayed,
                        f"{cite_id} has value {expected}, displayed {numeric}",
                    )
                )
    return ValidationResult(
        passed=not failures,
        text=working_text,
        failures=failures,
        auto_attached_count=auto_attached,
    )


def redact_uncited(text: str, failures: list[ValidationFailure]) -> str:
    redacted = text
    for failure in failures:
        if failure.reason in {"bad_cite", "bad_value", "parse"}:
            redacted = re.sub(r"<cite\s+[^>]+>.*?</cite>", "[uncited]", redacted, count=1, flags=re.DOTALL)
        elif failure.reason == "uncited":
            redacted = redacted.replace(failure.claim, "[uncited]", 1)
    return redacted


class CitationIndex:
    def __init__(self, tool_results: list[ToolResult]) -> None:
        self.aggregates = {
            aggregate.agg_id: aggregate.value
            for result in tool_results
            for aggregate in result.aggregates
        }
        self.rows = {
            row.row_id: row.values
            for result in tool_results
            for row in result.rows
        }

    def value_for(self, cite_id: str) -> int | float | None:
        base_id, _, field = cite_id.partition("#")
        if base_id.startswith("agg_"):
            return self.aggregates.get(base_id)
        values = self.rows.get(base_id)
        if values is None:
            return None
        if field:
            value = values.get(field)
            return value if isinstance(value, int | float) else None
        numeric_values = [value for value in values.values() if isinstance(value, int | float)]
        return numeric_values[0] if len(numeric_values) == 1 else None

    def unique_id_for_number(self, value: int | float) -> str | None:
        matches = [cite_id for cite_id, candidate in self.aggregates.items() if candidate == value]
        for row_id, values in self.rows.items():
            for value_field, candidate in values.items():
                if isinstance(candidate, int | float) and candidate == value:
                    matches.append(f"{row_id}#{value_field}")
        return matches[0] if len(matches) == 1 else None


def _auto_attach(text: str, index: CitationIndex) -> tuple[str, int]:
    output: list[str] = []
    count = 0
    cited_ranges = [match.span() for match in CITE_RE.finditer(text)]
    position = 0
    for match in NUMBER_RE.finditer(text):
        output.append(text[position : match.start()])
        token = match.group(0)
        if _inside_any(match.span(), cited_ranges) or _is_whitelisted_number(token, text, match.span()):
            output.append(token)
        else:
            value = _parse_display_number(token)
            cite_id = index.unique_id_for_number(value) if value is not None else None
            if cite_id:
                output.append(f"<cite {cite_id}>{token}</cite>")
                count += 1
            else:
                output.append(token)
        position = match.end()
    output.append(text[position:])
    return "".join(output), count


def _parse_display_number(value: str) -> int | float | None:
    match = NUMBER_RE.search(value)
    if not match:
        return None
    token = match.group(0).replace("₹", "").replace(",", "").replace("%", "").strip()
    parsed = float(token) if "." in token else int(token)
    return parsed


def _matches(expected: int | float, displayed: int | float, raw_display: str) -> bool:
    if "₹" in raw_display:
        return int(displayed * 100) == int(expected)
    return float(expected) == float(displayed)


def _inside_any(span: tuple[int, int], ranges: list[tuple[int, int]]) -> bool:
    return any(start <= span[0] and span[1] <= end for start, end in ranges)


def _is_whitelisted_number(token: str, text: str, span: tuple[int, int]) -> bool:
    if re.fullmatch(r"20\d{2}", token):
        before = text[max(0, span[0] - 2) : span[0]]
        after = text[span[1] : span[1] + 2]
        return "₹" not in before and "%" not in after
    return False
