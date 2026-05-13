from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text

from drishti.agents.rto_shipping_margin.agent import run_worker
from drishti.config import get_settings
from drishti.db.session import create_engine, set_merchant_context


@dataclass(frozen=True)
class MerchantSeed:
    key: str
    merchant_id: UUID
    name: str
    order_count: int


MERCHANTS = [
    MerchantSeed("merchant_a", UUID("00000000-0000-0000-0000-00000000000a"), "Merchant A", 6),
    MerchantSeed("merchant_b", UUID("00000000-0000-0000-0000-00000000000b"), "Merchant B", 18),
    MerchantSeed("merchant_c", UUID("00000000-0000-0000-0000-00000000000c"), "Merchant C", 12),
]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-agent", action="store_true")
    args = parser.parse_args()

    engine = create_engine(get_settings())
    async with engine.begin() as conn:
        for seed in MERCHANTS:
            await set_merchant_context(conn, seed.merchant_id)
            await seed_merchant(conn, seed)

    if args.run_agent:
        for seed in MERCHANTS:
            async with engine.begin() as conn:
                await set_merchant_context(conn, seed.merchant_id)
                result = await run_worker(conn, merchant_id=seed.merchant_id, trigger="manual")
                print(seed.key, result)

    await engine.dispose()


async def seed_merchant(conn, seed: MerchantSeed) -> None:
    await conn.execute(
        text(
            """
            INSERT INTO merchants (id, clerk_org_id, name, subdomain, time_zone, created_at, updated_at)
            VALUES (:merchant_id, :clerk_org_id, :name, :subdomain, 'Asia/Kolkata', now(), now())
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, updated_at = now()
            """
        ),
        {
            "merchant_id": str(seed.merchant_id),
            "clerk_org_id": f"org_{seed.key}",
            "name": seed.name,
            "subdomain": seed.key.replace("_", "-"),
        },
    )
    for index in range(1, seed.order_count + 1):
        await seed_order_bundle(conn, seed, index)

    if seed.key == "merchant_c":
        await seed_cod_rto_cluster(conn, seed)
        await seed_delayed_prepaid(conn, seed)
        await seed_refund_shipping_mismatch(conn, seed)


async def seed_order_bundle(conn, seed: MerchantSeed, index: int) -> None:
    order_id = _uuid("a0", seed, index)
    raw_id = _uuid("a1", seed, index)
    source_id = f"{seed.key}-order-{index}"
    total_paise = 75000 + (index * 12500)
    payment_method = "cod" if index % 3 == 0 else "prepaid"
    placed_at = datetime.now(UTC) - timedelta(days=index % 20)
    await insert_source_record(
        conn,
        seed=seed,
        raw_id=raw_id,
        source="shopify",
        resource="orders",
        source_record_id=source_id,
        payload={"id": source_id, "total_price": f"{total_paise / 100:.2f}"},
    )
    await conn.execute(
        text(
            """
            INSERT INTO orders (
                merchant_id, id, source, source_record_id, raw_record_id,
                placed_at, status, payment_method, total_paise, subtotal_paise,
                shipping_paise, tax_paise, discount_paise, currency, shipping_pincode,
                shipping_country, line_items_count, extras, synced_at, created_at, updated_at
            )
            VALUES (
                :merchant_id, :id, 'shopify', :source_record_id, :raw_id,
                :placed_at, 'confirmed', :payment_method, :total_paise, :subtotal_paise,
                5000, 0, 0, 'INR', :pincode, 'IN', 1,
                CAST(:extras AS jsonb), now(), now(), now()
            )
            ON CONFLICT (merchant_id, source, source_record_id)
            DO UPDATE SET total_paise = EXCLUDED.total_paise,
                          payment_method = EXCLUDED.payment_method,
                          placed_at = EXCLUDED.placed_at,
                          updated_at = now()
            """
        ),
        {
            "merchant_id": str(seed.merchant_id),
            "id": str(order_id),
            "source_record_id": source_id,
            "raw_id": str(raw_id),
            "placed_at": placed_at,
            "payment_method": payment_method,
            "total_paise": total_paise,
            "subtotal_paise": total_paise - 5000,
            "pincode": "110001" if index % 2 == 0 else "560001",
            "extras": json.dumps({"name": f"#{seed.key.upper()}-{index:04d}"}),
        },
    )


async def seed_cod_rto_cluster(conn, seed: MerchantSeed) -> None:
    for index in range(101, 106):
        order_id = _uuid("a2", seed, index)
        shipment_id = _uuid("a3", seed, index)
        link_id = _uuid("a4", seed, index)
        order_raw_id = _uuid("a5", seed, index)
        shipment_raw_id = _uuid("a6", seed, index)
        order_source_id = f"{seed.key}-rto-order-{index}"
        shipment_source_id = f"{seed.key}-rto-shipment-{index}"
        await insert_source_record(conn, seed=seed, raw_id=order_raw_id, source="shopify", resource="orders", source_record_id=order_source_id, payload={"id": order_source_id})
        await insert_source_record(conn, seed=seed, raw_id=shipment_raw_id, source="shiprocket", resource="shipments", source_record_id=shipment_source_id, payload={"id": shipment_source_id})
        await upsert_order(conn, seed, order_id, order_source_id, order_raw_id, "cod", 45000, "110001")
        await upsert_shipment(conn, seed, shipment_id, shipment_source_id, shipment_raw_id, "rto_initiated", 25000, "110001", picked_up_days=6)
        await upsert_link(conn, seed, link_id, order_id, shipment_id, None)


async def seed_delayed_prepaid(conn, seed: MerchantSeed) -> None:
    order_id = _uuid("a7", seed, 1)
    shipment_id = _uuid("a8", seed, 1)
    payment_id = _uuid("a9", seed, 1)
    link_id = _uuid("aa", seed, 1)
    await insert_source_record(conn, seed=seed, raw_id=_uuid("ab", seed, 1), source="shopify", resource="orders", source_record_id="merchant_c-delayed-order", payload={})
    await insert_source_record(conn, seed=seed, raw_id=_uuid("ac", seed, 1), source="shiprocket", resource="shipments", source_record_id="merchant_c-delayed-shipment", payload={})
    await insert_source_record(conn, seed=seed, raw_id=_uuid("ad", seed, 1), source="razorpay", resource="payments", source_record_id="merchant_c-delayed-payment", payload={})
    await upsert_order(conn, seed, order_id, "merchant_c-delayed-order", _uuid("ab", seed, 1), "prepaid", 175000, "400001")
    await upsert_shipment(conn, seed, shipment_id, "merchant_c-delayed-shipment", _uuid("ac", seed, 1), "in_transit", 14000, "400001", picked_up_days=7)
    await upsert_payment(conn, seed, payment_id, "merchant_c-delayed-payment", _uuid("ad", seed, 1), 175000)
    await upsert_link(conn, seed, link_id, order_id, shipment_id, payment_id)


async def seed_refund_shipping_mismatch(conn, seed: MerchantSeed) -> None:
    order_id = _uuid("ae", seed, 1)
    shipment_id = _uuid("af", seed, 1)
    payment_id = _uuid("b0", seed, 1)
    refund_id = _uuid("b1", seed, 1)
    link_id = _uuid("b2", seed, 1)
    await insert_source_record(conn, seed=seed, raw_id=_uuid("b3", seed, 1), source="shopify", resource="orders", source_record_id="merchant_c-refund-order", payload={})
    await insert_source_record(conn, seed=seed, raw_id=_uuid("b4", seed, 1), source="shiprocket", resource="shipments", source_record_id="merchant_c-refund-shipment", payload={})
    await insert_source_record(conn, seed=seed, raw_id=_uuid("b5", seed, 1), source="razorpay", resource="payments", source_record_id="merchant_c-refund-payment", payload={})
    await insert_source_record(conn, seed=seed, raw_id=_uuid("b6", seed, 1), source="razorpay", resource="refunds", source_record_id="merchant_c-refund", payload={})
    await upsert_order(conn, seed, order_id, "merchant_c-refund-order", _uuid("b3", seed, 1), "prepaid", 210000, "700001")
    await upsert_shipment(conn, seed, shipment_id, "merchant_c-refund-shipment", _uuid("b4", seed, 1), "in_transit", 18000, "700001", picked_up_days=5)
    await upsert_payment(conn, seed, payment_id, "merchant_c-refund-payment", _uuid("b5", seed, 1), 210000)
    await upsert_link(conn, seed, link_id, order_id, shipment_id, payment_id)
    await conn.execute(
        text(
            """
            INSERT INTO refunds (
                merchant_id, id, source, source_record_id, raw_record_id, payment_id,
                status, amount_paise, reason, processed_at, extras, synced_at, created_at, updated_at
            )
            VALUES (
                :merchant_id, :id, 'razorpay', 'merchant_c-refund', :raw_id, :payment_id,
                'processed', 210000, 'goodwill', now() - interval '1 day',
                '{}'::jsonb, now(), now(), now()
            )
            ON CONFLICT (merchant_id, source, source_record_id)
            DO UPDATE SET processed_at = EXCLUDED.processed_at, updated_at = now()
            """
        ),
        {"merchant_id": str(seed.merchant_id), "id": str(refund_id), "raw_id": str(_uuid("b6", seed, 1)), "payment_id": str(payment_id)},
    )


async def insert_source_record(conn, *, seed: MerchantSeed, raw_id: UUID, source: str, resource: str, source_record_id: str, payload: dict) -> None:
    await conn.execute(
        text(
            """
            INSERT INTO source_records (
                merchant_id, id, source, resource, source_record_id, endpoint,
                fetched_at, payload, payload_hash, created_at
            )
            VALUES (
                :merchant_id, :id, :source, :resource, :source_record_id, :endpoint,
                now(), CAST(:payload AS jsonb), :payload_hash, now()
            )
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "merchant_id": str(seed.merchant_id),
            "id": str(raw_id),
            "source": source,
            "resource": resource,
            "source_record_id": source_record_id,
            "endpoint": f"seed://demo/{source}/{resource}",
            "payload": json.dumps(payload),
            "payload_hash": f"demo-{source_record_id}",
        },
    )


async def upsert_order(conn, seed: MerchantSeed, order_id: UUID, source_id: str, raw_id: UUID, payment_method: str, total_paise: int, pincode: str) -> None:
    await conn.execute(
        text(
            """
            INSERT INTO orders (
                merchant_id, id, source, source_record_id, raw_record_id, placed_at,
                status, payment_method, total_paise, subtotal_paise, shipping_paise,
                tax_paise, discount_paise, currency, shipping_pincode, shipping_country,
                line_items_count, extras, synced_at, created_at, updated_at
            )
            VALUES (
                :merchant_id, :id, 'shopify', :source_id, :raw_id, now() - interval '5 days',
                'confirmed', :payment_method, :total_paise, :subtotal_paise, 3000,
                0, 0, 'INR', :pincode, 'IN', 1, '{}'::jsonb, now(), now(), now()
            )
            ON CONFLICT (merchant_id, source, source_record_id)
            DO UPDATE SET payment_method = EXCLUDED.payment_method,
                          total_paise = EXCLUDED.total_paise,
                          updated_at = now()
            """
        ),
        {
            "merchant_id": str(seed.merchant_id),
            "id": str(order_id),
            "source_id": source_id,
            "raw_id": str(raw_id),
            "payment_method": payment_method,
            "total_paise": total_paise,
            "subtotal_paise": total_paise - 3000,
            "pincode": pincode,
        },
    )


async def upsert_shipment(conn, seed: MerchantSeed, shipment_id: UUID, source_id: str, raw_id: UUID, status: str, freight_paise: int, pincode: str, *, picked_up_days: int) -> None:
    await conn.execute(
        text(
            """
            INSERT INTO shipments (
                merchant_id, id, source, source_record_id, raw_record_id, awb_code,
                courier_id, courier_name, status, freight_paise, weight_grams,
                pickup_pincode, delivery_pincode, picked_up_at, expected_delivery_at,
                rto_initiated_at, extras, synced_at, created_at, updated_at
            )
            VALUES (
                :merchant_id, :id, 'shiprocket', :source_id, :raw_id, :awb,
                'xb', 'Xpressbees', :status, :freight_paise, 500,
                '560001', :pincode, now() - (:picked_up_days * interval '1 day'),
                now() - interval '3 days',
                CASE WHEN :status LIKE 'rto%' THEN now() - interval '1 day' ELSE NULL END,
                '{}'::jsonb, now(), now(), now()
            )
            ON CONFLICT (merchant_id, source, source_record_id)
            DO UPDATE SET status = EXCLUDED.status,
                          freight_paise = EXCLUDED.freight_paise,
                          updated_at = now()
            """
        ),
        {
            "merchant_id": str(seed.merchant_id),
            "id": str(shipment_id),
            "source_id": source_id,
            "raw_id": str(raw_id),
            "awb": f"AWB-{source_id}",
            "status": status,
            "freight_paise": freight_paise,
            "pincode": pincode,
            "picked_up_days": picked_up_days,
        },
    )


async def upsert_payment(conn, seed: MerchantSeed, payment_id: UUID, source_id: str, raw_id: UUID, amount_paise: int) -> None:
    await conn.execute(
        text(
            """
            INSERT INTO payments (
                merchant_id, id, source, source_record_id, raw_record_id,
                status, method, amount_paise, fee_paise, tax_paise, net_paise,
                currency, captured_at, extras, synced_at, created_at, updated_at
            )
            VALUES (
                :merchant_id, :id, 'razorpay', :source_id, :raw_id,
                'captured', 'upi', :amount_paise, 0, 0, :amount_paise,
                'INR', now() - interval '4 days', '{}'::jsonb, now(), now(), now()
            )
            ON CONFLICT (merchant_id, source, source_record_id)
            DO UPDATE SET amount_paise = EXCLUDED.amount_paise, updated_at = now()
            """
        ),
        {"merchant_id": str(seed.merchant_id), "id": str(payment_id), "source_id": source_id, "raw_id": str(raw_id), "amount_paise": amount_paise},
    )


async def upsert_link(conn, seed: MerchantSeed, link_id: UUID, order_id: UUID, shipment_id: UUID, payment_id: UUID | None) -> None:
    await conn.execute(
        text(
            """
            INSERT INTO order_links (
                merchant_id, id, order_id, shipment_id, payment_id, linkage_method,
                confidence, created_at, updated_at
            )
            VALUES (
                :merchant_id, :id, :order_id, :shipment_id, :payment_id,
                'order_id_match', 1.0, now(), now()
            )
            ON CONFLICT (merchant_id, order_id)
            DO UPDATE SET shipment_id = EXCLUDED.shipment_id,
                          payment_id = COALESCE(EXCLUDED.payment_id, order_links.payment_id),
                          updated_at = now()
            """
        ),
        {
            "merchant_id": str(seed.merchant_id),
            "id": str(link_id),
            "order_id": str(order_id),
            "shipment_id": str(shipment_id),
            "payment_id": str(payment_id) if payment_id else None,
        },
    )


def _uuid(prefix: str, seed: MerchantSeed, index: int) -> UUID:
    suffix = {"merchant_a": "a", "merchant_b": "b", "merchant_c": "c"}[seed.key]
    return UUID(f"{prefix}000000-0000-0000-0000-00000000{suffix}{index:03d}")


if __name__ == "__main__":
    asyncio.run(main())
