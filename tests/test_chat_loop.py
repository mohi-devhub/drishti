from __future__ import annotations

from datetime import datetime
from uuid import UUID

import pytest

from drishti.chat.citation_validator import validate_citations
from drishti.chat.loop import (
    _answer_for,
    _coerce_tool_args,
    _db_validation_status,
    _openai_tool_schemas,
    _select_tools,
)
from drishti.chat.tools.registry import (
    CitedAggregate,
    CitedRow,
    ToolResult,
    update_duty_config,
    update_finding_status,
)
from drishti.routes.chat import _answer_chunks, _sse


MERCHANT_ID = UUID("00000000-0000-0000-0000-00000000000a")
FINDING_ID = UUID("00000000-0000-0000-0000-0000000000f1")


class _Mapping:
    def __init__(self, row: dict | None) -> None:
        self._row = row

    def one_or_none(self):
        return self._row

    def one(self):
        assert self._row is not None
        return self._row


class _Result:
    def __init__(self, row: dict | None) -> None:
        self._row = row

    def mappings(self):
        return _Mapping(self._row)


class _FakeSession:
    def __init__(self, rows: list[dict | None]) -> None:
        self._rows = list(rows)
        self.executed: list[tuple[str, dict]] = []
        self.commits = 0

    async def execute(self, statement, params):
        self.executed.append((str(statement), params))
        row = self._rows.pop(0) if self._rows else None
        return _Result(row)

    async def commit(self):
        self.commits += 1


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


@pytest.mark.asyncio
async def test_update_finding_status_returns_updated_row_and_commits() -> None:
    session = _FakeSession(
        rows=[
            {
                "id": FINDING_ID,
                "duty": "cod_rto_risk",
                "finding_type": "cod_rto_cluster",
                "severity": "high",
                "lifecycle_status": "acknowledged",
                "confidence": 0.92,
                "estimated_saving_inr_low": 1000,
                "estimated_saving_inr_high": 4000,
            }
        ]
    )

    result = await update_finding_status(
        session,
        merchant_id=MERCHANT_ID,
        finding_id=FINDING_ID,
        lifecycle_status="acknowledged",
    )

    assert result.tool_name == "update_finding_status"
    assert result.metadata["status"] == "updated"
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.row_id == f"finding:{FINDING_ID}"
    assert row.values["lifecycle_status"] == "acknowledged"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_update_finding_status_rejects_unknown_lifecycle_status() -> None:
    session = _FakeSession(rows=[])

    result = await update_finding_status(
        session,
        merchant_id=MERCHANT_ID,
        finding_id=FINDING_ID,
        lifecycle_status="archived",
    )

    assert result.metadata["status"] == "rejected"
    assert result.rows == []
    assert session.executed == []
    assert session.commits == 0


@pytest.mark.asyncio
async def test_update_finding_status_marks_not_found_when_row_missing() -> None:
    session = _FakeSession(rows=[None])

    result = await update_finding_status(
        session,
        merchant_id=MERCHANT_ID,
        finding_id=FINDING_ID,
        lifecycle_status="dismissed",
    )

    assert result.metadata["status"] == "not_found"
    assert result.rows == []
    assert session.commits == 1


@pytest.mark.asyncio
async def test_update_duty_config_returns_updated_row_and_commits() -> None:
    session = _FakeSession(
        rows=[
            {
                "duty": "delayed_prepaid",
                "enabled": False,
                "config": {},
                "updated_at": datetime(2026, 5, 17, 12, 0, 0),
            }
        ]
    )

    result = await update_duty_config(
        session,
        merchant_id=MERCHANT_ID,
        duty="delayed_prepaid",
        enabled=False,
    )

    assert result.tool_name == "update_duty_config"
    assert result.metadata["status"] == "updated"
    assert len(result.rows) == 1
    assert result.rows[0].values["enabled"] is False
    assert result.rows[0].values["duty"] == "delayed_prepaid"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_update_duty_config_rejects_unknown_duty() -> None:
    session = _FakeSession(rows=[])

    result = await update_duty_config(
        session,
        merchant_id=MERCHANT_ID,
        duty="invent_a_duty",
        enabled=True,
    )

    assert result.metadata["status"] == "rejected"
    assert result.rows == []
    assert session.executed == []
    assert session.commits == 0


def test_openai_schemas_expose_write_tools() -> None:
    names = {schema["name"] for schema in _openai_tool_schemas()}

    assert "update_finding_status" in names
    assert "update_duty_config" in names


def test_coerce_tool_args_handles_write_tools() -> None:
    finding_args = _coerce_tool_args(
        "update_finding_status",
        {
            "finding_id": "00000000-0000-0000-0000-0000000000f1",
            "lifecycle_status": "Dismissed",
        },
    )
    duty_args = _coerce_tool_args(
        "update_duty_config", {"duty": "delayed_prepaid", "enabled": "true"}
    )

    assert isinstance(finding_args["finding_id"], UUID)
    assert finding_args["lifecycle_status"] == "dismissed"
    assert duty_args == {"duty": "delayed_prepaid", "enabled": True}
