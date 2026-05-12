from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from drishti.chat.citation_validator import redact_uncited, validate_citations
from drishti.chat.tools.registry import ToolResult, query_orders
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

    normalized = message.lower()
    tool_results: list[ToolResult] = []
    if "revenue" in normalized or "total" in normalized:
        today = datetime.now(UTC).date()
        start_date = today.replace(day=1)
        started_at = datetime.now(UTC)
        orders = await query_orders(session, merchant_id=merchant_id, start_date=start_date)
        await chat_repo.create_tool_call(
            session,
            merchant_id=merchant_id,
            caller="chat",
            caller_id=user_message_id,
            tool_name=orders.tool_name,
            args=orders.args,
            result=orders.model_dump(),
            result_id=orders.result_id,
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )
        tool_results.append(orders)
        total_paise = next(agg.value for agg in orders.aggregates if agg.agg_id == "agg_orders_total_paise")
        count = next(agg.value for agg in orders.aggregates if agg.agg_id == "agg_orders_count")
        draft = (
            "Total revenue this month is "
            f"<cite agg_orders_total_paise>₹{int(total_paise) / 100:,.0f}</cite> "
            f"across <cite agg_orders_count>{count}</cite> orders."
        )
    else:
        started_at = datetime.now(UTC)
        orders = await query_orders(session, merchant_id=merchant_id, limit=10)
        await chat_repo.create_tool_call(
            session,
            merchant_id=merchant_id,
            caller="chat",
            caller_id=user_message_id,
            tool_name=orders.tool_name,
            args=orders.args,
            result=orders.model_dump(),
            result_id=orders.result_id,
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )
        tool_results.append(orders)
        count = next(agg.value for agg in orders.aggregates if agg.agg_id == "agg_orders_count")
        draft = f"I found <cite agg_orders_count>{count}</cite> recent orders for this merchant."

    validation = validate_citations(draft, tool_results)
    validation_status = "passed"
    if not validation.passed:
        retry = _retry_with_available_values(draft, tool_results)
        validation = validate_citations(retry, tool_results, auto_attach=False)
        validation_status = "retried" if validation.passed else "redacted"
    answer = validation.text if validation.passed else redact_uncited(validation.text, validation.failures)
    await chat_repo.create_tool_call(
        session,
        merchant_id=merchant_id,
        caller="chat",
        caller_id=user_message_id,
        tool_name="citation_validator",
        args={"draft": draft},
        result={"answer": answer},
        result_id=None,
        validation_status=validation_status,
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
        "validation_failures": [failure.__dict__ for failure in validation.failures],
        "tool_results": [result.model_dump() for result in tool_results],
    }


def _retry_with_available_values(_draft: str, tool_results: list[ToolResult]) -> str:
    if not tool_results:
        return "I do not have cited data for that yet."
    result = tool_results[-1]
    aggregate_parts = []
    for aggregate in result.aggregates:
        if aggregate.unit == "inr_paise":
            aggregate_parts.append(f"<cite {aggregate.agg_id}>₹{int(aggregate.value) / 100:,.0f}</cite>")
        else:
            aggregate_parts.append(f"<cite {aggregate.agg_id}>{aggregate.value}</cite>")
    if not aggregate_parts:
        return "I do not have cited data for that yet."
    return "Available cited values: " + ", ".join(aggregate_parts) + "."
