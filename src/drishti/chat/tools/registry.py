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


def _result_id() -> str:
    return f"tr_{uuid4().hex[:12]}"


def _iso(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value) if value else ""


def _date_args(**kwargs: Any) -> dict[str, Any]:
    return {key: value.isoformat() if hasattr(value, "isoformat") else value for key, value in kwargs.items()}
