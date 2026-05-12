from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest

from drishti.connectors.base import (
    Connector,
    ConnectorConnection,
    MockTransport,
    NoopRateLimiter,
    RateLimitConfig,
)


MERCHANT_ID = UUID("00000000-0000-0000-0000-00000000000a")
CONNECTION_ID = UUID("30000000-0000-0000-0000-000000000001")


class FakeConnector(Connector):
    source = "fake"
    base_url = "https://example.test"
    rate_limit_config = RateLimitConfig(requests_per_second=1, burst=1)

    async def authenticate(self) -> dict[str, str]:
        return {"authorization": "Bearer test"}

    async def refresh_credentials_if_needed(self) -> None:
        return None

    def syncer(self, resource: str):
        raise NotImplementedError


class RecordingLimiter(NoopRateLimiter):
    def __init__(self) -> None:
        self.buckets: list[str] = []

    async def acquire(self, bucket: str, config: RateLimitConfig) -> None:
        self.buckets.append(bucket)


@pytest.mark.asyncio
async def test_mock_transport_reads_matching_fixture(tmp_path: Path) -> None:
    fixture_path = tmp_path / "orders.json"
    fixture_path.write_text(
        json.dumps(
            {
                "request": {
                    "method": "GET",
                    "path": "/admin/api/2026-01/orders.json",
                    "params": {"status": "any"},
                },
                "response": {"status_code": 200, "json": {"orders": [{"id": 1}]}},
            }
        )
    )

    transport = MockTransport(tmp_path)
    response = await transport.request(
        "GET",
        "https://shop.test/admin/api/2026-01/orders.json",
        params={"status": "any", "limit": 250},
    )

    assert response.status_code == 200
    assert response.json()["orders"] == [{"id": 1}]


@pytest.mark.asyncio
async def test_connector_request_acquires_rate_limit_before_transport(tmp_path: Path) -> None:
    (tmp_path / "fixture.json").write_text(
        json.dumps(
            {
                "request": {"method": "GET", "path": "/resource", "params": {}},
                "response": {"status_code": 200, "json": {"ok": True}},
            }
        )
    )
    limiter = RecordingLimiter()
    connector = FakeConnector(
        ConnectorConnection(
            id=CONNECTION_ID,
            merchant_id=MERCHANT_ID,
            source="fake",
            auth_payload={},
            cursors={},
        ),
        MockTransport(tmp_path),
        limiter,
    )

    response = await connector.request("GET", "/resource")

    assert response.json() == {"ok": True}
    assert limiter.buckets == [f"{MERCHANT_ID}:fake"]
