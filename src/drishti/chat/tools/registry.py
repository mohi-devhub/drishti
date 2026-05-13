from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Awaitable, Callable
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class CitedRow(BaseModel):
    row_id: str
    values: dict[str, Any]
    source: str
    source_record_id: str
    raw_record_id: str
    fetched_from: str
    synced_at: str
    sync_run_id: str | None = None


class CitedAggregate(BaseModel):
    agg_id: str
    label: str
    value: int | float
    unit: str
    derived_from_row_ids: list[str] = Field(default_factory=list)
    formula: str


class ToolResult(BaseModel):
    result_id: str
    tool_name: str
    args: dict[str, Any]
    rows: list[CitedRow] = Field(default_factory=list)
    aggregates: list[CitedAggregate] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


ToolHandler = Callable[..., Awaitable[ToolResult]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    handler: ToolHandler
    read_only: bool = True
    description: str = ""


async def query_orders(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    start_date: date | None = None,
    end_date: date | None = None,
    status: str | None = None,
    payment_method: str | None = None,
    limit: int = 50,
) -> ToolResult:
    clauses = ["o.merchant_id = :merchant_id"]
    params: dict[str, Any] = {"merchant_id": str(merchant_id), "limit": limit}
    if start_date:
        clauses.append("o.placed_at >= :start_date")
        params["start_date"] = start_date
    if end_date:
        clauses.append("o.placed_at < :end_date")
        params["end_date"] = end_date
    if status:
        clauses.append("o.status = :status")
        params["status"] = status
    if payment_method:
        clauses.append("o.payment_method = :payment_method")
        params["payment_method"] = payment_method

    result = await session.execute(
        text(
            f"""
            SELECT
              o.id, o.source, o.source_record_id, o.raw_record_id, o.sync_run_id,
              o.placed_at, o.status, o.payment_method, o.total_paise, o.currency,
              o.shipping_pincode, o.synced_at, sr.endpoint
            FROM orders o
            JOIN source_records sr ON sr.id = o.raw_record_id AND sr.merchant_id = o.merchant_id
            WHERE {" AND ".join(clauses)}
            ORDER BY o.placed_at DESC
            LIMIT :limit
            """
        ),
        params,
    )
    rows = [_order_row(row) for row in result.mappings().all()]
    total = sum(int(row.values.get("total_paise") or 0) for row in rows)
    return ToolResult(
        result_id=_result_id(),
        tool_name="query_orders",
        args=_date_args(start_date=start_date, end_date=end_date, status=status, payment_method=payment_method),
        rows=rows,
        aggregates=[
            CitedAggregate(
                agg_id="agg_orders_count",
                label="orders_count",
                value=len(rows),
                unit="count",
                derived_from_row_ids=[row.row_id for row in rows],
                formula="COUNT(orders)",
            ),
            CitedAggregate(
                agg_id="agg_orders_total_paise",
                label="orders_total_paise",
                value=total,
                unit="inr_paise",
                derived_from_row_ids=[row.row_id for row in rows],
                formula="SUM(orders.total_paise)",
            ),
        ],
        metadata={"limit": limit},
    )


async def query_shipments(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    status: str | None = None,
    courier_id: str | None = None,
    limit: int = 50,
) -> ToolResult:
    clauses = ["s.merchant_id = :merchant_id"]
    params: dict[str, Any] = {"merchant_id": str(merchant_id), "limit": limit}
    if status:
        clauses.append("s.status = :status")
        params["status"] = status
    if courier_id:
        clauses.append("s.courier_id = :courier_id")
        params["courier_id"] = courier_id
    result = await session.execute(
        text(
            f"""
            SELECT s.*, sr.endpoint
            FROM shipments s
            JOIN source_records sr ON sr.id = s.raw_record_id AND sr.merchant_id = s.merchant_id
            WHERE {" AND ".join(clauses)}
            ORDER BY s.synced_at DESC
            LIMIT :limit
            """
        ),
        params,
    )
    rows = [_shipment_row(row) for row in result.mappings().all()]
    return ToolResult(
        result_id=_result_id(),
        tool_name="query_shipments",
        args={"status": status, "courier_id": courier_id},
        rows=rows,
        aggregates=[
            CitedAggregate(
                agg_id="agg_shipments_count",
                label="shipments_count",
                value=len(rows),
                unit="count",
                derived_from_row_ids=[row.row_id for row in rows],
                formula="COUNT(shipments)",
            )
        ],
    )


async def query_payments(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    status: str | None = None,
    limit: int = 50,
) -> ToolResult:
    clauses = ["p.merchant_id = :merchant_id"]
    params: dict[str, Any] = {"merchant_id": str(merchant_id), "limit": limit}
    if status:
        clauses.append("p.status = :status")
        params["status"] = status
    result = await session.execute(
        text(
            f"""
            SELECT p.*, sr.endpoint
            FROM payments p
            JOIN source_records sr ON sr.id = p.raw_record_id AND sr.merchant_id = p.merchant_id
            WHERE {" AND ".join(clauses)}
            ORDER BY p.captured_at DESC NULLS LAST
            LIMIT :limit
            """
        ),
        params,
    )
    rows = [_payment_row(row) for row in result.mappings().all()]
    total = sum(int(row.values.get("amount_paise") or 0) for row in rows)
    return ToolResult(
        result_id=_result_id(),
        tool_name="query_payments",
        args={"status": status},
        rows=rows,
        aggregates=[
            CitedAggregate(
                agg_id="agg_payments_total_paise",
                label="payments_total_paise",
                value=total,
                unit="inr_paise",
                derived_from_row_ids=[row.row_id for row in rows],
                formula="SUM(payments.amount_paise)",
            )
        ],
    )


async def query_rto_loss_by_pincode(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    limit: int = 20,
) -> ToolResult:
    result = await session.execute(
        text(
            """
            SELECT
              COALESCE(o.shipping_pincode, s.delivery_pincode) AS pincode,
              COUNT(*) AS order_count,
              COALESCE(SUM(o.total_paise), 0) AS order_total_paise,
              COALESCE(SUM(s.freight_paise), 0) AS freight_total_paise
            FROM order_links ol
            JOIN orders o ON o.id = ol.order_id AND o.merchant_id = ol.merchant_id
            JOIN shipments s ON s.id = ol.shipment_id AND s.merchant_id = ol.merchant_id
            WHERE ol.merchant_id = :merchant_id
              AND s.status LIKE 'rto%'
              AND ol.confidence >= 0.8
            GROUP BY 1
            ORDER BY freight_total_paise DESC
            LIMIT :limit
            """
        ),
        {"merchant_id": str(merchant_id), "limit": limit},
    )
    rows = []
    aggregates = []
    for row in result.mappings().all():
        row_id = f"rto_pincode:{row['pincode']}"
        rows.append(
            CitedRow(
                row_id=row_id,
                values=dict(row),
                source="derived",
                source_record_id=str(row["pincode"]),
                raw_record_id="",
                fetched_from="orders JOIN shipments",
                synced_at=datetime.now().isoformat(),
                sync_run_id=None,
            )
        )
        aggregates.append(
            CitedAggregate(
                agg_id=f"agg_rto_loss_{row['pincode']}",
                label=f"rto_loss_pincode_{row['pincode']}",
                value=int(row["freight_total_paise"] or 0),
                unit="inr_paise",
                derived_from_row_ids=[row_id],
                formula="SUM(shipments.freight_paise WHERE shipments.status LIKE 'rto%')",
            )
        )
    return ToolResult(
        result_id=_result_id(),
        tool_name="rto_loss_by_pincode",
        args={"limit": limit},
        rows=rows,
        aggregates=aggregates,
    )


async def courier_margin_by_route(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    limit: int = 20,
) -> ToolResult:
    result = await session.execute(
        text(
            """
            SELECT
              LEFT(pickup_pincode, 3) || '_' || LEFT(delivery_pincode, 3) AS route,
              courier_id,
              courier_name,
              COUNT(*) AS shipment_count,
              COALESCE(SUM(freight_paise), 0) AS freight_total_paise,
              AVG(freight_paise::numeric / NULLIF(weight_grams, 0)) AS freight_per_g
            FROM shipments
            WHERE merchant_id = :merchant_id
              AND weight_grams > 0
              AND freight_paise IS NOT NULL
            GROUP BY 1, 2, 3
            ORDER BY freight_total_paise DESC
            LIMIT :limit
            """
        ),
        {"merchant_id": str(merchant_id), "limit": limit},
    )
    rows = [
        _derived_row(
            row_id=f"courier_route:{row['courier_id']}:{row['route']}",
            values=dict(row),
            fetched_from="shipments GROUP BY route,courier",
        )
        for row in result.mappings().all()
    ]
    return ToolResult(
        result_id=_result_id(),
        tool_name="courier_margin_by_route",
        args={"limit": limit},
        rows=rows,
        aggregates=[
            CitedAggregate(
                agg_id="agg_courier_routes_count",
                label="courier_routes_count",
                value=len(rows),
                unit="count",
                derived_from_row_ids=[row.row_id for row in rows],
                formula="COUNT(route,courier groups)",
            )
        ],
    )


async def delayed_prepaid_orders(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    limit: int = 50,
) -> ToolResult:
    result = await session.execute(
        text(
            """
            SELECT s.id AS shipment_id, o.id AS order_id, p.id AS payment_id,
                   s.awb_code, s.courier_name, s.expected_delivery_at,
                   EXTRACT(day FROM now() - s.expected_delivery_at)::int AS days_overdue,
                   o.total_paise
            FROM shipments s
            JOIN order_links ol ON ol.shipment_id = s.id
              AND ol.merchant_id = s.merchant_id
              AND ol.confidence >= 0.8
            JOIN orders o ON o.id = ol.order_id AND o.merchant_id = ol.merchant_id
            JOIN payments p ON p.id = ol.payment_id AND p.merchant_id = ol.merchant_id
            WHERE s.merchant_id = :merchant_id
              AND s.status NOT IN ('delivered', 'cancelled', 'rto_delivered', 'lost')
              AND s.expected_delivery_at < now() - interval '2 days'
              AND p.status = 'captured'
            ORDER BY days_overdue DESC
            LIMIT :limit
            """
        ),
        {"merchant_id": str(merchant_id), "limit": limit},
    )
    rows = [
        _derived_row(
            row_id=f"delayed_prepaid:{row['shipment_id']}",
            values=dict(row),
            fetched_from="shipments JOIN orders JOIN payments",
        )
        for row in result.mappings().all()
    ]
    return ToolResult(
        result_id=_result_id(),
        tool_name="delayed_prepaid_orders",
        args={"limit": limit},
        rows=rows,
        aggregates=[
            CitedAggregate(
                agg_id="agg_delayed_prepaid_count",
                label="delayed_prepaid_count",
                value=len(rows),
                unit="count",
                derived_from_row_ids=[row.row_id for row in rows],
                formula="COUNT(delayed prepaid shipments)",
            )
        ],
    )


async def refund_shipping_mismatch_check(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    limit: int = 50,
) -> ToolResult:
    result = await session.execute(
        text(
            """
            SELECT r.id AS refund_id, o.id AS order_id, s.id AS shipment_id,
                   r.amount_paise AS refund_amount_paise,
                   COALESCE(s.freight_paise, 0) AS freight_paise,
                   r.amount_paise + COALESCE(s.freight_paise, 0) AS exposure_paise
            FROM refunds r
            JOIN payments p ON p.id = r.payment_id AND p.merchant_id = r.merchant_id
            JOIN order_links ol ON ol.payment_id = p.id
              AND ol.merchant_id = p.merchant_id
              AND ol.confidence >= 0.8
            JOIN orders o ON o.id = ol.order_id AND o.merchant_id = ol.merchant_id
            JOIN shipments s ON s.id = ol.shipment_id AND s.merchant_id = ol.merchant_id
            WHERE r.merchant_id = :merchant_id
              AND s.picked_up_at IS NOT NULL
              AND r.processed_at IS NOT NULL
              AND s.picked_up_at < r.processed_at
              AND s.status NOT IN ('rto_delivered', 'rto_initiated', 'rto_in_transit')
            ORDER BY exposure_paise DESC
            LIMIT :limit
            """
        ),
        {"merchant_id": str(merchant_id), "limit": limit},
    )
    rows = [
        _derived_row(
            row_id=f"refund_shipping:{row['refund_id']}",
            values=dict(row),
            fetched_from="refunds JOIN payments JOIN orders JOIN shipments",
        )
        for row in result.mappings().all()
    ]
    exposure = sum(int(row.values.get("exposure_paise") or 0) for row in rows)
    return ToolResult(
        result_id=_result_id(),
        tool_name="refund_shipping_mismatch_check",
        args={"limit": limit},
        rows=rows,
        aggregates=[
            CitedAggregate(
                agg_id="agg_refund_shipping_exposure_paise",
                label="refund_shipping_exposure_paise",
                value=exposure,
                unit="inr_paise",
                derived_from_row_ids=[row.row_id for row in rows],
                formula="SUM(refund.amount_paise + shipment.freight_paise)",
            )
        ],
    )


async def list_findings(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    limit: int = 50,
) -> ToolResult:
    result = await session.execute(
        text(
            """
            SELECT id, duty, finding_type, severity, confidence,
                   estimated_saving_inr_low, estimated_saving_inr_high, narrative_status
            FROM agent_findings
            WHERE merchant_id = :merchant_id
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        {"merchant_id": str(merchant_id), "limit": limit},
    )
    rows = [
        _derived_row(
            row_id=f"finding:{row['id']}",
            values=dict(row),
            fetched_from="agent_findings",
        )
        for row in result.mappings().all()
    ]
    return ToolResult(
        result_id=_result_id(),
        tool_name="list_findings",
        args={"limit": limit},
        rows=rows,
        aggregates=[
            CitedAggregate(
                agg_id="agg_findings_count",
                label="findings_count",
                value=len(rows),
                unit="count",
                derived_from_row_ids=[row.row_id for row in rows],
                formula="COUNT(agent_findings)",
            )
        ],
    )


async def get_finding(
    session: AsyncSession,
    *,
    merchant_id: UUID,
    finding_id: UUID,
) -> ToolResult:
    result = await session.execute(
        text(
            """
            SELECT id, duty, finding_type, severity, confidence,
                   estimated_saving_inr_low, estimated_saving_inr_high,
                   narrative, narrative_status, proposed_action, citations
            FROM agent_findings
            WHERE merchant_id = :merchant_id
              AND id = :finding_id
            """
        ),
        {"merchant_id": str(merchant_id), "finding_id": str(finding_id)},
    )
    row = result.mappings().one_or_none()
    rows = [
        _derived_row(row_id=f"finding:{row['id']}", values=dict(row), fetched_from="agent_findings")
    ] if row else []
    return ToolResult(
        result_id=_result_id(),
        tool_name="get_finding",
        args={"finding_id": str(finding_id)},
        rows=rows,
        aggregates=[],
    )


TOOL_REGISTRY: dict[str, ToolDefinition] = {
    "query_orders": ToolDefinition(
        name="query_orders",
        handler=query_orders,
        description="Filter merchant orders and return cited rows plus count/revenue aggregates.",
    ),
    "rto_loss_by_pincode": ToolDefinition(
        name="rto_loss_by_pincode",
        handler=query_rto_loss_by_pincode,
        description="Group RTO freight loss by pincode using linked orders and shipments.",
    ),
    "query_shipments": ToolDefinition(
        name="query_shipments",
        handler=query_shipments,
        description="Filter merchant shipments and return cited shipment rows.",
    ),
    "query_payments": ToolDefinition(
        name="query_payments",
        handler=query_payments,
        description="Filter merchant payments and return cited payment rows plus payment aggregates.",
    ),
    "courier_margin_by_route": ToolDefinition(
        name="courier_margin_by_route",
        handler=courier_margin_by_route,
        description="Group freight cost by route and courier.",
    ),
    "delayed_prepaid_orders": ToolDefinition(
        name="delayed_prepaid_orders",
        handler=delayed_prepaid_orders,
        description="Find prepaid shipments past expected delivery.",
    ),
    "refund_shipping_mismatch_check": ToolDefinition(
        name="refund_shipping_mismatch_check",
        handler=refund_shipping_mismatch_check,
        description="Find refunds issued after shipment pickup.",
    ),
    "list_findings": ToolDefinition(
        name="list_findings",
        handler=list_findings,
        description="List agent findings for the current merchant.",
    ),
    "get_finding": ToolDefinition(
        name="get_finding",
        handler=get_finding,
        description="Get one agent finding.",
    ),
}


def _order_row(row: Any) -> CitedRow:
    row_id = f"order:{row['id']}"
    return CitedRow(
        row_id=row_id,
        values={
            "placed_at": _iso(row["placed_at"]),
            "status": row["status"],
            "payment_method": row["payment_method"],
            "total_paise": int(row["total_paise"]),
            "currency": row["currency"],
            "shipping_pincode": row["shipping_pincode"],
        },
        source=row["source"],
        source_record_id=row["source_record_id"],
        raw_record_id=str(row["raw_record_id"]),
        fetched_from=row["endpoint"],
        synced_at=_iso(row["synced_at"]),
        sync_run_id=str(row["sync_run_id"]) if row["sync_run_id"] else None,
    )


def _shipment_row(row: Any) -> CitedRow:
    return CitedRow(
        row_id=f"shipment:{row['id']}",
        values={
            "awb_code": row["awb_code"],
            "courier_name": row["courier_name"],
            "status": row["status"],
            "freight_paise": row["freight_paise"],
            "delivery_pincode": row["delivery_pincode"],
        },
        source=row["source"],
        source_record_id=row["source_record_id"],
        raw_record_id=str(row["raw_record_id"]),
        fetched_from=row["endpoint"],
        synced_at=_iso(row["synced_at"]),
        sync_run_id=str(row["sync_run_id"]) if row["sync_run_id"] else None,
    )


def _payment_row(row: Any) -> CitedRow:
    return CitedRow(
        row_id=f"payment:{row['id']}",
        values={
            "status": row["status"],
            "method": row["method"],
            "amount_paise": int(row["amount_paise"]),
            "fee_paise": row["fee_paise"],
            "net_paise": row["net_paise"],
            "captured_at": _iso(row["captured_at"]),
        },
        source=row["source"],
        source_record_id=row["source_record_id"],
        raw_record_id=str(row["raw_record_id"]),
        fetched_from=row["endpoint"],
        synced_at=_iso(row["synced_at"]),
        sync_run_id=str(row["sync_run_id"]) if row["sync_run_id"] else None,
    )


def _derived_row(*, row_id: str, values: dict[str, Any], fetched_from: str) -> CitedRow:
    return CitedRow(
        row_id=row_id,
        values={key: _json_safe(value) for key, value in values.items()},
        source="derived",
        source_record_id=row_id,
        raw_record_id="",
        fetched_from=fetched_from,
        synced_at=datetime.now().isoformat(),
    )


def _result_id() -> str:
    return f"tr_{uuid4().hex[:12]}"


def _iso(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value) if value else ""


def _date_args(**kwargs: Any) -> dict[str, Any]:
    return {key: value.isoformat() if hasattr(value, "isoformat") else value for key, value in kwargs.items()}


def _json_safe(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
