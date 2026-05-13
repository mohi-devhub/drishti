from __future__ import annotations

import base64
import hashlib
import hmac

import pytest

from drishti.agents.rto_shipping_margin.agent import build_agent
from drishti.agents.rto_shipping_margin.duties.common import finding_tool_result
from drishti.agents.rto_shipping_margin.narrator import narrate
from drishti.agents.base import Finding
from drishti.chat.tools.registry import TOOL_REGISTRY
from drishti.webhooks.shopify import resource_from_topic, verify_hmac
from drishti.worker import WorkerSettings
from drishti.workers.agent_worker import (
    agent_daily_run,
    enqueue_daily_agent_runs,
    run_rto_shipping_margin_agent,
)


def test_agent_has_four_day4_duties() -> None:
    agent = build_agent()

    assert [duty.name for duty in agent.duties] == [
        "cod_rto_risk",
        "courier_margin_drift",
        "delayed_prepaid",
        "refund_shipping_mismatch",
    ]


def test_agent_worker_entrypoints_are_named() -> None:
    assert run_rto_shipping_margin_agent.__name__ == "run_rto_shipping_margin_agent"
    assert agent_daily_run.__name__ == "agent_daily_run"
    assert enqueue_daily_agent_runs.__name__ == "enqueue_daily_agent_runs"


def test_worker_settings_declares_agent_cron() -> None:
    assert any(job.name == "enqueue_daily_agent_runs" for job in WorkerSettings.cron_jobs)


def test_day4_chat_tools_are_read_only() -> None:
    expected = {
        "query_orders",
        "rto_loss_by_pincode",
        "query_shipments",
        "query_payments",
        "courier_margin_by_route",
        "delayed_prepaid_orders",
        "refund_shipping_mismatch_check",
        "list_findings",
        "get_finding",
    }

    assert set(TOOL_REGISTRY) == expected
    assert all(tool.read_only for tool in TOOL_REGISTRY.values())


def test_shopify_webhook_hmac_validation() -> None:
    body = b'{"id": 123}'
    secret = "shopify-secret"
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    header = base64.b64encode(digest).decode("ascii")

    assert verify_hmac(body=body, header=header, secret=secret) is True
    assert verify_hmac(body=body, header="bad", secret=secret) is False
    assert verify_hmac(body=body, header=None, secret=None) is True


def test_shopify_topic_maps_to_resource() -> None:
    assert resource_from_topic("orders/create") == "orders"
    assert resource_from_topic("customers/update") == "customers"
    assert resource_from_topic("products/create") == "products"


@pytest.mark.asyncio
async def test_agent_narration_validates_savings_citations() -> None:
    tool_result = finding_tool_result(
        tool_name="test_duty",
        row_id="finding:test",
        values={"cluster": "1100"},
        evidence_row_ids=["order:1", "shipment:1"],
        estimated_low_inr=1200,
        estimated_high_inr=1500,
    )
    finding = Finding(
        duty="cod_rto_risk",
        finding_type="cod_rto_pincode_cluster",
        severity="medium",
        confidence=0.9,
        evidence_row_ids=["order:1", "shipment:1"],
        estimated_saving_inr_low=1200,
        estimated_saving_inr_high=1500,
        tool_result=tool_result,
    )

    narrative, status, _ = await narrate(finding)

    assert status == "validated"
    assert "₹1,200" in narrative
