from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import logfire
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from drishti.chat.citation_validator import redact_uncited, validate_citations
from drishti.config import get_settings
from drishti.chat.tools.registry import TOOL_REGISTRY, ToolDefinition, ToolResult
from drishti.db.repositories import chat as chat_repo


async def run_chat_turn(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    message: str,
    clerk_user_id: str = "system",
    chat_session_id: UUID | None = None,
) -> dict:
    if chat_session_id is None:
        chat_session_id = await chat_repo.create_session(
            session,
            merchant_id=merchant_id,
            clerk_user_id=clerk_user_id,
            title=message[:80],
        )
    user_message_id = await chat_repo.insert_message(
        session,
        merchant_id=merchant_id,
        session_id=chat_session_id,
        role="user",
        content=message,
    )
    await session.commit()

    tool_results, draft, mode, openai_status = await _draft_answer(
        session,
        merchant_id=merchant_id,
        caller_id=user_message_id,
        message=message,
    )

    validation = validate_citations(draft, tool_results)
    validation_status = "passed" if mode == "deterministic" else "openai_passed"
    if not validation.passed and mode == "openai":
        draft = _answer_for(message, tool_results)
        validation = validate_citations(draft, tool_results)
        validation_status = (
            "openai_fallback_passed" if validation.passed else "openai_fallback_failed"
        )
    if not validation.passed:
        retry = _retry_with_available_values(draft, tool_results)
        validation = validate_citations(retry, tool_results, auto_attach=False)
        validation_status = "retried" if validation.passed else "redacted"
    answer = (
        validation.text
        if validation.passed
        else redact_uncited(validation.text, validation.failures)
    )
    await chat_repo.create_tool_call(
        session,
        merchant_id=merchant_id,
        caller="chat",
        caller_id=user_message_id,
        tool_name="citation_validator",
        args={"draft": draft, "mode": mode},
        result={"answer": answer, "openai_status": openai_status},
        result_id=None,
        validation_status=_db_validation_status(validation_status),
        validation_failures=[failure.__dict__ for failure in validation.failures],
    )
    assistant_message_id = await chat_repo.insert_message(
        session,
        merchant_id=merchant_id,
        session_id=chat_session_id,
        role="assistant",
        content=answer,
    )
    return {
        "session_id": str(chat_session_id),
        "message_id": str(assistant_message_id),
        "answer": answer,
        "validation_status": validation_status,
        "openai_status": openai_status,
        "validation_failures": [failure.__dict__ for failure in validation.failures],
        "tool_results": [result.model_dump() for result in tool_results],
    }


async def _draft_answer(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    caller_id: UUID,
    message: str,
) -> tuple[list[ToolResult], str, str, str]:
    settings = get_settings()
    if settings.openai_api_key:
        openai_result = await _openai_tool_draft(
            session,
            merchant_id=merchant_id,
            caller_id=caller_id,
            message=message,
            model=settings.openai_chat_model,
            api_key=settings.openai_api_key,
        )
        if openai_result is not None:
            return openai_result[0], openai_result[1], "openai", "ok"
        openai_status = "openai_error"
    else:
        openai_status = "not_configured"
    tool_results = await _run_selected_tools(
        session,
        merchant_id=merchant_id,
        caller_id=caller_id,
        selected_tools=_select_tools(message),
        message=message,
    )
    return tool_results, _answer_for(message, tool_results), "deterministic", openai_status


async def _run_selected_tools(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    caller_id: UUID,
    selected_tools: list[tuple[str, dict[str, Any]]],
    message: str,
) -> list[ToolResult]:
    tool_results: list[ToolResult] = []
    for tool_name, args in selected_tools:
        result = await _run_tool(
            session,
            merchant_id=merchant_id,
            caller_id=caller_id,
            tool=TOOL_REGISTRY[tool_name],
            args=args,
        )
        tool_results.append(result)

        if tool_name == "list_findings" and _wants_latest_finding(message) and result.rows:
            finding_id = result.rows[0].values.get("id")
            if finding_id:
                tool_results.append(
                    await _run_tool(
                        session,
                        merchant_id=merchant_id,
                        caller_id=caller_id,
                        tool=TOOL_REGISTRY["get_finding"],
                        args={"finding_id": UUID(str(finding_id))},
                    )
                )

    return tool_results


async def _openai_tool_draft(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    caller_id: UUID,
    message: str,
    model: str,
    api_key: str,
) -> tuple[list[ToolResult], str] | None:
    client = AsyncOpenAI(api_key=api_key)
    input_items: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You are Drishti, an ops analyst for D2C merchants. "
                f"The current date is {datetime.now(UTC).date().isoformat()}. "
                "Resolve relative date phrases like 'this month' against that date. "
                "Answer using the provided tools. Every numeric value in your final answer "
                "must be copied from a tool result and wrapped as <cite id>number</cite>. "
                "Do not invent arithmetic or cite IDs. If a number is unavailable, omit it."
            ),
        },
        {"role": "user", "content": message},
    ]
    try:
        response = await _create_openai_response_with_retry(
            client,
            model=model,
            input=input_items,
            tools=_openai_tool_schemas(),
        )
        tool_results: list[ToolResult] = []
        for _ in range(3):
            calls = _function_calls(response)
            if not calls:
                return tool_results, response.output_text or ""
            input_items.extend(_response_output_items(response))
            for call in calls:
                result = await _run_openai_tool_call(
                    session,
                    merchant_id=merchant_id,
                    caller_id=caller_id,
                    call=call,
                )
                if result:
                    tool_results.append(result)
                    output = result.model_dump_json()
                else:
                    output = json.dumps({"error": "Tool call rejected"})
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": _call_attr(call, "call_id"),
                        "output": output,
                    }
                )
            response = await _create_openai_response_with_retry(
                client,
                model=model,
                input=input_items,
                tools=_openai_tool_schemas(),
            )
    except Exception as exc:
        logfire.exception(
            "OpenAI chat tool loop failed; falling back to deterministic routing",
            error_type=type(exc).__name__,
        )
        return None
    return tool_results, response.output_text or ""


async def _create_openai_response_with_retry(
    client: AsyncOpenAI,
    *,
    model: str,
    input: list[dict[str, Any]],
    tools: list[dict[str, Any]],
):
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            return await client.responses.create(model=model, input=input, tools=tools)
        except Exception as exc:
            last_exc = exc
            logfire.warning(
                "OpenAI response attempt failed",
                attempt=attempt + 1,
                error_type=type(exc).__name__,
            )
            if attempt < 2:
                await asyncio.sleep(0.4 * (2**attempt))
    assert last_exc is not None
    raise last_exc


def _openai_tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": "query_orders",
            "description": TOOL_REGISTRY["query_orders"].description,
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "status": {"type": "string", "enum": ["confirmed", "cancelled", "refunded"]},
                    "payment_method": {"type": "string", "enum": ["cod", "prepaid"]},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "rto_loss_by_pincode",
            "description": TOOL_REGISTRY["rto_loss_by_pincode"].description,
            "parameters": _limit_schema(),
        },
        {
            "type": "function",
            "name": "query_shipments",
            "description": TOOL_REGISTRY["query_shipments"].description,
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "courier_id": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "query_payments",
            "description": TOOL_REGISTRY["query_payments"].description,
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "courier_margin_by_route",
            "description": TOOL_REGISTRY["courier_margin_by_route"].description,
            "parameters": _limit_schema(),
        },
        {
            "type": "function",
            "name": "delayed_prepaid_orders",
            "description": TOOL_REGISTRY["delayed_prepaid_orders"].description,
            "parameters": _limit_schema(),
        },
        {
            "type": "function",
            "name": "refund_shipping_mismatch_check",
            "description": TOOL_REGISTRY["refund_shipping_mismatch_check"].description,
            "parameters": _limit_schema(),
        },
        {
            "type": "function",
            "name": "list_findings",
            "description": TOOL_REGISTRY["list_findings"].description,
            "parameters": _limit_schema(),
        },
        {
            "type": "function",
            "name": "get_finding",
            "description": TOOL_REGISTRY["get_finding"].description,
            "parameters": {
                "type": "object",
                "properties": {"finding_id": {"type": "string", "format": "uuid"}},
                "required": ["finding_id"],
                "additionalProperties": False,
            },
        },
    ]


def _limit_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
        "additionalProperties": False,
    }


async def _run_openai_tool_call(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    caller_id: UUID,
    call: Any,
) -> ToolResult | None:
    name = _call_attr(call, "name")
    if name not in TOOL_REGISTRY:
        return None
    args = _coerce_tool_args(name, _call_args(call))
    return await _run_tool(
        session,
        merchant_id=merchant_id,
        caller_id=caller_id,
        tool=TOOL_REGISTRY[name],
        args=args,
    )


def _function_calls(response: Any) -> list[Any]:
    return [
        item
        for item in getattr(response, "output", [])
        if _call_attr(item, "type") == "function_call"
    ]


def _response_output_items(response: Any) -> list[dict[str, Any]]:
    items = []
    for item in getattr(response, "output", []):
        if hasattr(item, "model_dump"):
            items.append(item.model_dump())
        elif isinstance(item, dict):
            items.append(item)
    return items


def _call_args(call: Any) -> dict[str, Any]:
    raw = _call_attr(call, "arguments") or "{}"
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _call_attr(call: Any, name: str) -> Any:
    if isinstance(call, dict):
        return call.get(name)
    return getattr(call, name, None)


def _coerce_tool_args(name: str, args: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "query_orders": {"start_date", "end_date", "status", "payment_method", "limit"},
        "query_shipments": {"status", "courier_id", "limit"},
        "query_payments": {"status", "limit"},
        "get_finding": {"finding_id"},
    }.get(name, {"limit"})
    coerced = {key: value for key, value in args.items() if key in allowed and value is not None}
    if "limit" in coerced:
        coerced["limit"] = max(1, min(100, int(coerced["limit"])))
    if name == "query_orders" and "status" in coerced:
        status = str(coerced["status"]).lower()
        if status in {"confirmed", "cancelled", "refunded"}:
            coerced["status"] = status
        else:
            coerced.pop("status", None)
    for key in ("start_date", "end_date"):
        if key in coerced and isinstance(coerced[key], str):
            coerced[key] = date.fromisoformat(coerced[key])
    if name == "get_finding" and "finding_id" in coerced:
        coerced["finding_id"] = UUID(str(coerced["finding_id"]))
    return coerced


def _retry_with_available_values(_draft: str, tool_results: list[ToolResult]) -> str:
    if not tool_results:
        return "I do not have cited data for that yet."
    result = tool_results[-1]
    aggregate_parts = []
    for aggregate in result.aggregates:
        if aggregate.unit == "inr_paise":
            aggregate_parts.append(
                f"<cite {aggregate.agg_id}>₹{int(aggregate.value) / 100:,.0f}</cite>"
            )
        else:
            aggregate_parts.append(f"<cite {aggregate.agg_id}>{aggregate.value}</cite>")
    if not aggregate_parts:
        return "I do not have cited data for that yet."
    return "Available cited values: " + ", ".join(aggregate_parts) + "."


def _db_validation_status(status: str) -> str:
    if status in {"passed", "retried", "redacted", "pending"}:
        return status
    if status in {"openai_passed", "openai_fallback_passed"}:
        return "passed"
    if status == "openai_fallback_failed":
        return "retried"
    return "pending"


async def _run_tool(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    caller_id: UUID,
    tool: ToolDefinition,
    args: dict[str, Any],
) -> ToolResult:
    started_at = datetime.now(UTC)
    result = await tool.handler(session, merchant_id=merchant_id, **args)
    await chat_repo.create_tool_call(
        session,
        merchant_id=merchant_id,
        caller="chat",
        caller_id=caller_id,
        tool_name=result.tool_name,
        args=result.args,
        result=result.model_dump(),
        result_id=result.result_id,
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )
    await session.commit()
    return result


def _select_tools(message: str) -> list[tuple[str, dict[str, Any]]]:
    normalized = message.lower()
    tools: list[tuple[str, dict[str, Any]]] = []

    if _mentions_any(normalized, "revenue", "sales", "orders", "total"):
        args: dict[str, Any] = {"limit": 100}
        if _mentions_any(normalized, "month", "monthly", "this month"):
            today = datetime.now(UTC).date()
            args["start_date"] = date(today.year, today.month, 1)
        tools.append(("query_orders", args))

    if _mentions_any(normalized, "rto", "cod", "losing money", "shipping leakage", "leakage"):
        tools.append(("rto_loss_by_pincode", {"limit": 10}))

    if _mentions_any(normalized, "courier", "lane", "route", "freight", "margin"):
        tools.append(("courier_margin_by_route", {"limit": 10}))

    if _mentions_any(normalized, "delay", "delayed", "stuck", "late", "sla"):
        tools.append(("delayed_prepaid_orders", {"limit": 10}))

    if _mentions_any(normalized, "refund", "refunded", "mismatch"):
        tools.append(("refund_shipping_mismatch_check", {"limit": 10}))

    if _mentions_any(normalized, "finding", "findings", "agent", "evidence", "latest"):
        tools.append(("list_findings", {"limit": 10}))

    if not tools:
        tools.append(("query_orders", {"limit": 10}))
    return _dedupe_tools(tools)


def _answer_for(message: str, tool_results: list[ToolResult]) -> str:
    by_name = {result.tool_name: result for result in tool_results}
    normalized = message.lower()
    sections: list[str] = []

    if orders := by_name.get("query_orders"):
        sections.append(_orders_answer(orders))
    if rto := by_name.get("rto_loss_by_pincode"):
        sections.append(_rto_answer(rto))
    if courier := by_name.get("courier_margin_by_route"):
        sections.append(_courier_answer(courier))
    if delayed := by_name.get("delayed_prepaid_orders"):
        sections.append(_delayed_answer(delayed))
    if refunds := by_name.get("refund_shipping_mismatch_check"):
        sections.append(_refund_answer(refunds))
    if finding := by_name.get("get_finding"):
        sections.append(_finding_detail_answer(finding))
    elif findings := by_name.get("list_findings"):
        sections.append(_findings_answer(findings))

    answer_sections = [section for section in sections if section]
    if answer_sections:
        return " ".join(answer_sections)
    if "help" in normalized:
        return "I can answer cited questions about revenue, RTO loss, courier freight, delayed prepaid shipments, refunds, and agent findings."
    return "I do not have cited data for that yet."


def _orders_answer(result: ToolResult) -> str:
    count = _aggregate(result, "agg_orders_count")
    total = _aggregate(result, "agg_orders_total_paise")
    if not count or not total or total.value == 0:
        return ""
    return (
        "Order revenue for the selected scope is "
        f"{_cite_money(total.agg_id, total.value)} across "
        f"<cite {count.agg_id}>{int(count.value)}</cite> orders."
    )


def _rto_answer(result: ToolResult) -> str:
    total = _aggregate(result, "agg_rto_loss_total_paise")
    if not total or total.value == 0 or not result.rows:
        return ""
    leading = result.rows[0]
    freight_cite = f"{leading.row_id}#freight_total_paise"
    count_cite = f"{leading.row_id}#order_count"
    return (
        "RTO shipping loss is concentrated in the highest-loss destination group: "
        f"{_cite_money(freight_cite, leading.values.get('freight_total_paise', 0))} over "
        f"<cite {count_cite}>{leading.values.get('order_count', 0)}</cite> linked orders. "
        f"Total cited RTO freight loss is {_cite_money(total.agg_id, total.value)}."
    )


def _courier_answer(result: ToolResult) -> str:
    total = _aggregate(result, "agg_courier_freight_total_paise")
    groups = _aggregate(result, "agg_courier_routes_count")
    if not total or total.value == 0 or not result.rows:
        return ""
    leading = result.rows[0]
    courier_name = leading.values.get("courier_name") or "the leading courier"
    return (
        f"{courier_name} is the largest cited courier-route cost group, with "
        f"{_cite_money(leading.row_id + '#freight_total_paise', leading.values.get('freight_total_paise', 0))} "
        f"in freight. The tool returned <cite {groups.agg_id}>{int(groups.value)}</cite> route groups "
        f"and {_cite_money(total.agg_id, total.value)} in cited freight."
    )


def _delayed_answer(result: ToolResult) -> str:
    count = _aggregate(result, "agg_delayed_prepaid_count")
    if not count or count.value == 0 or not result.rows:
        return ""
    leading = result.rows[0]
    return (
        "The most overdue prepaid shipment is "
        f"<cite {leading.row_id}#days_overdue>{leading.values.get('days_overdue', 0)}</cite> days overdue "
        f"on an order worth {_cite_money(leading.row_id + '#total_paise', leading.values.get('total_paise', 0))}. "
        f"The cited delayed prepaid queue has <cite {count.agg_id}>{int(count.value)}</cite> shipments."
    )


def _refund_answer(result: ToolResult) -> str:
    exposure = _aggregate(result, "agg_refund_shipping_exposure_paise")
    count = _aggregate(result, "agg_refund_shipping_count")
    if not exposure or exposure.value == 0 or not result.rows:
        return ""
    leading = result.rows[0]
    return (
        "Refund-shipping exposure totals "
        f"{_cite_money(exposure.agg_id, exposure.value)} across "
        f"<cite {count.agg_id}>{int(count.value)}</cite> cited cases. "
        "The largest case exposes "
        f"{_cite_money(leading.row_id + '#exposure_paise', leading.values.get('exposure_paise', 0))}."
    )


def _findings_answer(result: ToolResult) -> str:
    count = _aggregate(result, "agg_findings_count")
    if not count or count.value == 0 or not result.rows:
        return ""
    leading = result.rows[0]
    low = leading.values.get("estimated_saving_inr_low")
    high = leading.values.get("estimated_saving_inr_high")
    if isinstance(low, int | float) and isinstance(high, int | float):
        return (
            f"The agent has <cite {count.agg_id}>{int(count.value)}</cite> cited findings. "
            "The latest finding has an estimated savings range of Rs "
            f"<cite {leading.row_id}#estimated_saving_inr_low>{int(low):,}</cite> to Rs "
            f"<cite {leading.row_id}#estimated_saving_inr_high>{int(high):,}</cite>."
        )
    return f"The agent has <cite {count.agg_id}>{int(count.value)}</cite> cited findings."


def _finding_detail_answer(result: ToolResult) -> str:
    if not result.rows:
        return "I did not find a cited latest finding to inspect."
    row = result.rows[0]
    low = row.values.get("estimated_saving_inr_low")
    high = row.values.get("estimated_saving_inr_high")
    confidence = row.values.get("confidence")
    parts = ["The latest finding is available with cited estimates."]
    if isinstance(low, int | float) and isinstance(high, int | float):
        parts.append(
            "Estimated savings are Rs "
            f"<cite {row.row_id}#estimated_saving_inr_low>{int(low):,}</cite> to Rs "
            f"<cite {row.row_id}#estimated_saving_inr_high>{int(high):,}</cite>."
        )
    if isinstance(confidence, int | float):
        parts.append(f"Confidence is <cite {row.row_id}#confidence>{confidence}</cite>.")
    return " ".join(parts)


def _aggregate(result: ToolResult, agg_id: str):
    return next((aggregate for aggregate in result.aggregates if aggregate.agg_id == agg_id), None)


def _cite_money(cite_id: str, value: Any) -> str:
    paise = int(value or 0)
    return f"<cite {cite_id}>₹{paise / 100:,.0f}</cite>"


def _mentions_any(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)


def _wants_latest_finding(message: str) -> bool:
    normalized = message.lower()
    return _mentions_any(normalized, "latest", "evidence", "behind", "detail")


def _dedupe_tools(tools: list[tuple[str, dict[str, Any]]]) -> list[tuple[str, dict[str, Any]]]:
    seen: set[str] = set()
    deduped: list[tuple[str, dict[str, Any]]] = []
    for name, args in tools:
        if name in seen:
            continue
        seen.add(name)
        deduped.append((name, args))
    return deduped
