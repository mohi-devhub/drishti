from __future__ import annotations

from drishti.chat.citation_validator import redact_uncited, validate_citations
from drishti.chat.tools.registry import CitedAggregate, CitedRow, TOOL_REGISTRY, ToolResult


def tool_result() -> ToolResult:
    return ToolResult(
        result_id="tr_test",
        tool_name="query_orders",
        args={},
        rows=[
            CitedRow(
                row_id="order:ord_1",
                values={"total_paise": 49900, "line_items_count": 2},
                source="shopify",
                source_record_id="523",
                raw_record_id="raw_1",
                fetched_from="GET /orders",
                synced_at="2026-05-12T00:00:00Z",
            )
        ],
        aggregates=[
            CitedAggregate(
                agg_id="agg_total",
                label="total",
                value=204800,
                unit="inr_paise",
                derived_from_row_ids=["order:ord_1"],
                formula="SUM(total_paise)",
            ),
            CitedAggregate(
                agg_id="agg_count",
                label="count",
                value=3,
                unit="count",
                derived_from_row_ids=["order:ord_1"],
                formula="COUNT(*)",
            ),
        ],
    )


def test_validator_accepts_cited_currency_and_count() -> None:
    result = validate_citations(
        "Revenue is <cite agg_total>₹2,048</cite> across <cite agg_count>3</cite> orders.",
        [tool_result()],
    )

    assert result.passed is True


def test_validator_rejects_uncited_numbers() -> None:
    result = validate_citations("Revenue is ₹2,048 across 3 orders.", [tool_result()], auto_attach=False)

    assert result.passed is False
    assert {failure.reason for failure in result.failures} == {"uncited"}


def test_validator_rejects_bad_ids_and_values() -> None:
    result = validate_citations("Revenue is <cite agg_missing>₹2,048</cite>.", [tool_result()])
    mismatch = validate_citations("Revenue is <cite agg_total>₹2,049</cite>.", [tool_result()])

    assert result.passed is False
    assert result.failures[0].reason == "bad_cite"
    assert mismatch.passed is False
    assert mismatch.failures[0].reason == "bad_value"


def test_validator_accepts_explicit_row_field_cites() -> None:
    result = validate_citations("One order was <cite order:ord_1#total_paise>₹499</cite>.", [tool_result()])

    assert result.passed is True


def test_validator_auto_attaches_unambiguous_values() -> None:
    result = validate_citations("There were 3 orders.", [tool_result()])

    assert result.passed is True
    assert result.auto_attached_count == 1
    assert "<cite agg_count>3</cite>" in result.text


def test_redact_uncited_hides_failed_values() -> None:
    result = validate_citations("Revenue is ₹2,048.", [tool_result()], auto_attach=False)

    assert redact_uncited(result.text, result.failures) == "Revenue is [uncited]."


def test_validator_allows_plain_years_but_not_currency_year_shaped_numbers() -> None:
    year = validate_citations("In 2026, revenue changed.", [tool_result()], auto_attach=False)
    money = validate_citations("Revenue was ₹2026.", [tool_result()], auto_attach=False)

    assert year.passed is True
    assert money.passed is False


def test_validator_rejects_ambiguous_auto_attach() -> None:
    result = tool_result()
    result.aggregates.append(
        CitedAggregate(
            agg_id="agg_other_count",
            label="other_count",
            value=3,
            unit="count",
            derived_from_row_ids=[],
            formula="COUNT(other)",
        )
    )

    validation = validate_citations("There were 3 cases.", [result])

    assert validation.passed is False
    assert validation.auto_attached_count == 0


def test_validator_rejects_row_cites_without_unambiguous_numeric_field() -> None:
    result = validate_citations("Order value was <cite order:ord_1>₹499</cite>.", [tool_result()])

    assert result.passed is False
    assert result.failures[0].reason == "bad_cite"


def test_validator_accepts_percent_aggregate() -> None:
    result = tool_result()
    result.aggregates.append(
        CitedAggregate(
            agg_id="agg_rto_rate",
            label="rto_rate",
            value=12.5,
            unit="percent",
            derived_from_row_ids=["order:ord_1"],
            formula="100 * rto / orders",
        )
    )

    validation = validate_citations("RTO rate was <cite agg_rto_rate>12.5%</cite>.", [result])

    assert validation.passed is True


def test_day3_tool_registry_exposes_only_read_only_starter_tools() -> None:
    assert set(TOOL_REGISTRY) == {
        "query_orders",
        "rto_loss_by_pincode",
        "query_shipments",
        "query_payments",
    }
    assert all(tool.read_only for tool in TOOL_REGISTRY.values())
