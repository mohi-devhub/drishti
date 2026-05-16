from __future__ import annotations

from drishti.chat.citation_validator import validate_citations
from drishti.chat.loop import _answer_for, _coerce_tool_args, _db_validation_status, _select_tools
from drishti.chat.tools.registry import CitedAggregate, CitedRow, ToolResult
from drishti.routes.chat import _answer_chunks, _sse


def test_chat_selects_cross_source_tools_for_shipping_loss_question() -> None:
    selected = _select_tools("Which courier lanes are losing money from shipping leakage?")

    assert ("rto_loss_by_pincode", {"limit": 10}) in selected
    assert ("courier_margin_by_route", {"limit": 10}) in selected


def test_rto_answer_is_fully_cited() -> None:
    result = ToolResult(
        result_id="tr_rto",
        tool_name="rto_loss_by_pincode",
        args={"limit": 10},
        rows=[
            CitedRow(
                row_id="rto_pincode:110001",
                values={"order_count": 5, "freight_total_paise": 125000},
                source="derived",
                source_record_id="rto_pincode:110001",
                raw_record_id="",
                fetched_from="orders JOIN shipments",
                synced_at="2026-05-14T00:00:00Z",
            )
        ],
        aggregates=[
            CitedAggregate(
                agg_id="agg_rto_loss_total_paise",
                label="rto_loss_total_paise",
                value=125000,
                unit="inr_paise",
                derived_from_row_ids=["rto_pincode:110001"],
                formula="SUM(shipments.freight_paise)",
            )
        ],
    )

    answer = _answer_for("Where is RTO risk concentrated?", [result])
    validation = validate_citations(answer, [result], auto_attach=False)

    assert validation.passed is True
    assert "₹1,250" in answer


def test_openai_tool_args_are_bounded_and_coerced() -> None:
    args = _coerce_tool_args(
        "query_orders",
        {"start_date": "2026-05-01", "limit": 500, "merchant_id": "bad"},
    )

    assert args["start_date"].isoformat() == "2026-05-01"
    assert args["limit"] == 100
    assert "merchant_id" not in args


def test_openai_validation_status_maps_to_database_allowed_values() -> None:
    assert _db_validation_status("openai_passed") == "passed"
    assert _db_validation_status("openai_fallback_passed") == "passed"
    assert _db_validation_status("openai_fallback_failed") == "retried"


def test_empty_tool_sections_do_not_pollute_useful_fallback_answer() -> None:
    empty_orders = ToolResult(
        result_id="tr_orders",
        tool_name="query_orders",
        args={},
        rows=[],
        aggregates=[
            CitedAggregate(
                agg_id="agg_orders_count",
                label="orders_count",
                value=0,
                unit="count",
                derived_from_row_ids=[],
                formula="COUNT(orders)",
            ),
            CitedAggregate(
                agg_id="agg_orders_total_paise",
                label="orders_total_paise",
                value=0,
                unit="inr_paise",
                derived_from_row_ids=[],
                formula="SUM(orders.total_paise)",
            ),
        ],
    )
    rto = ToolResult(
        result_id="tr_rto",
        tool_name="rto_loss_by_pincode",
        args={},
        rows=[
            CitedRow(
                row_id="rto_pincode:110001",
                values={"order_count": 10, "freight_total_paise": 250000},
                source="derived",
                source_record_id="110001",
                raw_record_id="",
                fetched_from="orders JOIN shipments",
                synced_at="2026-05-14T00:00:00Z",
            )
        ],
        aggregates=[
            CitedAggregate(
                agg_id="agg_rto_loss_total_paise",
                label="rto_loss_total_paise",
                value=250000,
                unit="inr_paise",
                derived_from_row_ids=["rto_pincode:110001"],
                formula="SUM(shipments.freight_paise)",
            )
        ],
    )

    answer = _answer_for("Which COD orders are losing money from RTO?", [empty_orders, rto])

    assert "did not find cited order revenue" not in answer
    assert "RTO shipping loss" in answer


def test_sse_helpers_emit_event_frames_and_answer_chunks() -> None:
    frame = _sse("delta", {"text": "hello"})
    chunks = _answer_chunks("one two three four five six seven eight nine ten")

    assert frame.startswith("event: delta\n")
    assert 'data: {"text": "hello"}' in frame
    assert "".join(chunks).replace("  ", " ").strip() == "one two three four five six seven eight nine ten"
