from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

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
    rto_clusters: int
    delayed_orders: int
    refund_mismatches: int
    courier_routes: int


MERCHANTS = [
    MerchantSeed(
        "merchant_a", UUID("00000000-0000-0000-0000-00000000000a"), "Merchant A", 250, 1, 2, 1, 1
    ),
    MerchantSeed(
        "merchant_b", UUID("00000000-0000-0000-0000-00000000000b"), "Merchant B", 1000, 2, 4, 2, 2
    ),
    MerchantSeed(
        "merchant_c", UUID("00000000-0000-0000-0000-00000000000c"), "Merchant C", 2500, 3, 7, 4, 3
    ),
]

BASE_PINCODES = ["122001", "560001", "600001", "700001", "500081", "411045"]
RTO_PINCODES = ["302001", "411001", "380001"]
ROUTE_PAIRS = [("560001", "302001"), ("122001", "411001"), ("500081", "380001")]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-agent", action="store_true")
    parser.add_argument(
        "--merchant",
        choices=[seed.key for seed in MERCHANTS],
        help="Seed only one demo merchant. Defaults to all merchants.",
    )
    args = parser.parse_args()
    selected = [seed for seed in MERCHANTS if args.merchant in (None, seed.key)]

    engine = create_engine(get_settings())
    async with engine.begin() as conn:
        for seed in selected:
            print(f"seeding {seed.key} ({seed.order_count} baseline orders)")
            await set_merchant_context(conn, seed.merchant_id)
            await seed_merchant(conn, seed)

    if args.run_agent:
        for seed in selected:
            async with engine.begin() as conn:
                print(f"running agent {seed.key}")
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
        if index <= 20:
            await seed_order_bundle(conn, seed, index)
    await seed_background_orders(conn, seed)

    await seed_cod_rto_clusters(conn, seed)
    await seed_courier_margin_drift(conn, seed)
    await seed_delayed_prepaid(conn, seed)
    await seed_refund_shipping_mismatch(conn, seed)


async def seed_order_bundle(conn, seed: MerchantSeed, index: int) -> None:
    order_id = _uuid("a0", seed, index)
    raw_id = _uuid("a1", seed, index)
    shipment_id = _uuid("c0", seed, index)
    shipment_raw_id = _uuid("c1", seed, index)
    payment_id = _uuid("c2", seed, index)
    payment_raw_id = _uuid("c3", seed, index)
    link_id = _uuid("c4", seed, index)
    source_id = f"{seed.key}-order-{index}"
    shipment_source_id = f"{seed.key}-shipment-{index}"
    payment_source_id = f"{seed.key}-payment-{index}"
    total_paise = 75000 + (index * 12500)
    payment_method = "cod" if index % 3 == 0 else "prepaid"
    placed_at = datetime.now(UTC) - timedelta(days=index % 20)
    pincode = BASE_PINCODES[index % len(BASE_PINCODES)]
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
            "pincode": pincode,
            "extras": json.dumps({"name": f"#{seed.key.upper()}-{index:04d}"}),
        },
    )
    await insert_source_record(
        conn,
        seed=seed,
        raw_id=shipment_raw_id,
        source="shiprocket",
        resource="shipments",
        source_record_id=shipment_source_id,
        payload={"id": shipment_source_id, "awb": f"AWB-{shipment_source_id}"},
    )
    await insert_source_record(
        conn,
        seed=seed,
        raw_id=payment_raw_id,
        source="razorpay",
        resource="payments",
        source_record_id=payment_source_id,
        payload={"id": payment_source_id, "amount": f"{total_paise / 100:.2f}"},
    )
    await upsert_shipment(
        conn,
        seed,
        shipment_id,
        shipment_source_id,
        shipment_raw_id,
        "delivered",
        9000 + ((index % 7) * 700),
        pincode,
        picked_up_days=2 + (index % 5),
        courier_id="sf" if index % 4 == 0 else "dl",
        courier_name="Shadowfax" if index % 4 == 0 else "Delhivery",
        pickup_pincode=BASE_PINCODES[(index + 1) % len(BASE_PINCODES)],
        weight_grams=450 + ((index % 5) * 100),
    )
    await upsert_payment(
        conn,
        seed,
        payment_id,
        payment_source_id,
        payment_raw_id,
        total_paise,
        method="cod" if payment_method == "cod" else "upi",
    )
    await upsert_link(conn, seed, link_id, order_id, shipment_id, payment_id)


async def seed_background_orders(conn, seed: MerchantSeed) -> None:
    if seed.order_count <= 20:
        return
    await conn.execute(
        text(
            """
            WITH generated AS (
                SELECT
                    generate_series(21, :order_count)::int AS index
            ),
            background AS (
                SELECT
                    index,
                    md5(:seed_key || '-background-order-' || index)::uuid AS order_id,
                    md5(:seed_key || '-background-order-raw-' || index)::uuid AS order_raw_id,
                    md5(:seed_key || '-background-shipment-' || index)::uuid AS shipment_id,
                    md5(:seed_key || '-background-shipment-raw-' || index)::uuid AS shipment_raw_id,
                    md5(:seed_key || '-background-payment-' || index)::uuid AS payment_id,
                    md5(:seed_key || '-background-payment-raw-' || index)::uuid AS payment_raw_id,
                    md5(:seed_key || '-background-link-' || index)::uuid AS link_id,
                    :seed_key || '-background-order-' || index AS order_source_id,
                    :seed_key || '-background-shipment-' || index AS shipment_source_id,
                    :seed_key || '-background-payment-' || index AS payment_source_id,
                    CASE WHEN index % 3 = 0 THEN 'cod' ELSE 'prepaid' END AS payment_method,
                    75000 + (index * 12500) AS total_paise,
                    9000 + ((index % 7) * 700) AS freight_paise,
                    (ARRAY['122001', '560001', '600001', '700001', '500081', '411045'])[1 + (index % 6)] AS delivery_pincode,
                    (ARRAY['122001', '560001', '600001', '700001', '500081', '411045'])[1 + ((index + 1) % 6)] AS pickup_pincode,
                    450 + ((index % 5) * 100) AS weight_grams
                FROM generated
            ),
            inserted_order_raw AS (
                INSERT INTO source_records (
                    merchant_id, id, source, resource, source_record_id, endpoint,
                    fetched_at, payload, payload_hash, created_at
                )
                SELECT
                    :merchant_id,
                    order_raw_id,
                    'shopify',
                    'orders',
                    order_source_id,
                    'seed://demo/shopify/orders',
                    now(),
                    jsonb_build_object(
                        'id', order_source_id,
                        'total_price', to_char(total_paise / 100.0, 'FM999999990.00'),
                        'payment_method', payment_method,
                        'shipping_address', jsonb_build_object('zip', delivery_pincode, 'country', 'IN')
                    ),
                    'demo-' || order_source_id,
                    now()
                FROM background
                ON CONFLICT (id) DO NOTHING
            ),
            inserted_shipment_raw AS (
                INSERT INTO source_records (
                    merchant_id, id, source, resource, source_record_id, endpoint,
                    fetched_at, payload, payload_hash, created_at
                )
                SELECT
                    :merchant_id,
                    shipment_raw_id,
                    'shiprocket',
                    'shipments',
                    shipment_source_id,
                    'seed://demo/shiprocket/shipments',
                    now(),
                    jsonb_build_object(
                        'id', shipment_source_id,
                        'awb', 'AWB-' || shipment_source_id,
                        'freight', freight_paise,
                        'status', 'delivered',
                        'delivery_pincode', delivery_pincode
                    ),
                    'demo-' || shipment_source_id,
                    now()
                FROM background
                ON CONFLICT (id) DO NOTHING
            ),
            inserted_payment_raw AS (
                INSERT INTO source_records (
                    merchant_id, id, source, resource, source_record_id, endpoint,
                    fetched_at, payload, payload_hash, created_at
                )
                SELECT
                    :merchant_id,
                    payment_raw_id,
                    'razorpay',
                    'payments',
                    payment_source_id,
                    'seed://demo/razorpay/payments',
                    now(),
                    jsonb_build_object(
                        'id', payment_source_id,
                        'amount', total_paise,
                        'method', CASE WHEN payment_method = 'cod' THEN 'cod' ELSE 'upi' END,
                        'status', 'captured'
                    ),
                    'demo-' || payment_source_id,
                    now()
                FROM background
                ON CONFLICT (id) DO NOTHING
            ),
            inserted_orders AS (
            INSERT INTO orders (
                merchant_id, id, source, source_record_id, raw_record_id,
                placed_at, status, payment_method, total_paise, subtotal_paise,
                shipping_paise, tax_paise, discount_paise, currency, shipping_pincode,
                shipping_country, line_items_count, extras, synced_at, created_at, updated_at
            )
            SELECT
                :merchant_id,
                order_id,
                'shopify',
                order_source_id,
                order_raw_id,
                now() - ((index % 20) * interval '1 day'),
                'confirmed',
                payment_method,
                total_paise,
                total_paise - 5000,
                5000,
                0,
                0,
                'INR',
                delivery_pincode,
                'IN',
                1,
                jsonb_build_object('name', '#' || upper(:seed_key) || '-' || lpad(index::text, 4, '0')),
                now(),
                now(),
                now()
            FROM background
            ON CONFLICT (merchant_id, source, source_record_id)
            DO UPDATE SET total_paise = EXCLUDED.total_paise,
                          payment_method = EXCLUDED.payment_method,
                          placed_at = EXCLUDED.placed_at,
                          shipping_pincode = EXCLUDED.shipping_pincode,
                          updated_at = now()
            ),
            inserted_shipments AS (
                INSERT INTO shipments (
                    merchant_id, id, source, source_record_id, raw_record_id, awb_code,
                    courier_id, courier_name, status, freight_paise, weight_grams,
                    pickup_pincode, delivery_pincode, picked_up_at, expected_delivery_at,
                    rto_initiated_at, extras, synced_at, created_at, updated_at
                )
                SELECT
                    :merchant_id,
                    shipment_id,
                    'shiprocket',
                    shipment_source_id,
                    shipment_raw_id,
                    'AWB-' || shipment_source_id,
                    CASE WHEN index % 4 = 0 THEN 'sf' ELSE 'dl' END,
                    CASE WHEN index % 4 = 0 THEN 'Shadowfax' ELSE 'Delhivery' END,
                    'delivered',
                    freight_paise,
                    weight_grams,
                    pickup_pincode,
                    delivery_pincode,
                    now() - ((2 + (index % 5)) * interval '1 day'),
                    now() - interval '1 day',
                    NULL,
                    '{}'::jsonb,
                    now(),
                    now(),
                    now()
                FROM background
                ON CONFLICT (merchant_id, source, source_record_id)
                DO UPDATE SET status = EXCLUDED.status,
                              freight_paise = EXCLUDED.freight_paise,
                              courier_id = EXCLUDED.courier_id,
                              courier_name = EXCLUDED.courier_name,
                              pickup_pincode = EXCLUDED.pickup_pincode,
                              delivery_pincode = EXCLUDED.delivery_pincode,
                              weight_grams = EXCLUDED.weight_grams,
                              updated_at = now()
            ),
            inserted_payments AS (
                INSERT INTO payments (
                    merchant_id, id, source, source_record_id, raw_record_id,
                    status, method, amount_paise, fee_paise, tax_paise, net_paise,
                    currency, captured_at, extras, synced_at, created_at, updated_at
                )
                SELECT
                    :merchant_id,
                    payment_id,
                    'razorpay',
                    payment_source_id,
                    payment_raw_id,
                    'captured',
                    CASE WHEN payment_method = 'cod' THEN 'cod' ELSE 'upi' END,
                    total_paise,
                    0,
                    0,
                    total_paise,
                    'INR',
                    now() - ((index % 20) * interval '1 day'),
                    '{}'::jsonb,
                    now(),
                    now(),
                    now()
                FROM background
                ON CONFLICT (merchant_id, source, source_record_id)
                DO UPDATE SET method = EXCLUDED.method,
                              amount_paise = EXCLUDED.amount_paise,
                              updated_at = now()
            )
            INSERT INTO order_links (
                merchant_id, id, order_id, shipment_id, payment_id, linkage_method,
                confidence, created_at, updated_at
            )
            SELECT
                :merchant_id,
                link_id,
                order_id,
                shipment_id,
                payment_id,
                'order_id_match',
                1.0,
                now(),
                now()
            FROM background
            ON CONFLICT (merchant_id, order_id)
            DO UPDATE SET shipment_id = EXCLUDED.shipment_id,
                          payment_id = EXCLUDED.payment_id,
                          updated_at = now()
            """
        ),
        {
            "merchant_id": str(seed.merchant_id),
            "seed_key": seed.key,
            "order_count": seed.order_count,
        },
    )


async def seed_cod_rto_clusters(conn, seed: MerchantSeed) -> None:
    for cluster in range(seed.rto_clusters):
        pincode = RTO_PINCODES[cluster % len(RTO_PINCODES)]
        start = 3100 + (cluster * 100)
        await seed_cod_rto_cluster(conn, seed, start=start, count=8 + cluster, pincode=pincode)


async def seed_cod_rto_cluster(
    conn, seed: MerchantSeed, *, start: int, count: int, pincode: str
) -> None:
    for index in range(start, start + count):
        order_id = _uuid("a2", seed, index)
        shipment_id = _uuid("a3", seed, index)
        link_id = _uuid("a4", seed, index)
        order_raw_id = _uuid("a5", seed, index)
        shipment_raw_id = _uuid("a6", seed, index)
        order_source_id = f"{seed.key}-rto-order-{index}"
        shipment_source_id = f"{seed.key}-rto-shipment-{index}"
        await insert_source_record(
            conn,
            seed=seed,
            raw_id=order_raw_id,
            source="shopify",
            resource="orders",
            source_record_id=order_source_id,
            payload={"id": order_source_id},
        )
        await insert_source_record(
            conn,
            seed=seed,
            raw_id=shipment_raw_id,
            source="shiprocket",
            resource="shipments",
            source_record_id=shipment_source_id,
            payload={"id": shipment_source_id},
        )
        offset = index - start
        await upsert_order(
            conn,
            seed,
            order_id,
            order_source_id,
            order_raw_id,
            "cod",
            42000 + (offset * 500),
            pincode,
        )
        await upsert_shipment(
            conn,
            seed,
            shipment_id,
            shipment_source_id,
            shipment_raw_id,
            "rto_initiated",
            22000 + (offset * 500),
            pincode,
            picked_up_days=6,
        )
        await upsert_link(conn, seed, link_id, order_id, shipment_id, None)


async def seed_courier_margin_drift(conn, seed: MerchantSeed) -> None:
    for route_index in range(seed.courier_routes):
        pickup_pincode, delivery_pincode = ROUTE_PAIRS[route_index % len(ROUTE_PAIRS)]
        start = 4200 + (route_index * 100)
        rows = [
            *[
                (start + index, "xb", "Xpressbees", 34000 + (route_index * 2000))
                for index in range(0, 7)
            ],
            *[
                (start + 20 + index, "dl", "Delhivery", 11500 + (route_index * 1000))
                for index in range(0, 7)
            ],
        ]
        for offset, courier_id, courier_name, freight_paise in rows:
            shipment_id = _uuid("b7", seed, offset)
            raw_id = _uuid("b8", seed, offset)
            source_id = f"{seed.key}-courier-margin-shipment-{offset}"
            await insert_source_record(
                conn,
                seed=seed,
                raw_id=raw_id,
                source="shiprocket",
                resource="shipments",
                source_record_id=source_id,
                payload={"id": source_id, "courier": courier_name, "freight": freight_paise},
            )
            await upsert_shipment(
                conn,
                seed,
                shipment_id,
                source_id,
                raw_id,
                "delivered",
                freight_paise,
                delivery_pincode,
                picked_up_days=3,
                courier_id=courier_id,
                courier_name=courier_name,
                pickup_pincode=pickup_pincode,
                weight_grams=500,
            )


async def seed_delayed_prepaid(conn, seed: MerchantSeed) -> None:
    for item in range(1, seed.delayed_orders + 1):
        index = 5200 + item
        order_id = _uuid("a7", seed, index)
        shipment_id = _uuid("a8", seed, index)
        payment_id = _uuid("a9", seed, index)
        link_id = _uuid("aa", seed, index)
        order_raw_id = _uuid("ab", seed, index)
        shipment_raw_id = _uuid("ac", seed, index)
        payment_raw_id = _uuid("ad", seed, index)
        order_source_id = f"{seed.key}-delayed-order-{item}"
        shipment_source_id = f"{seed.key}-delayed-shipment-{item}"
        payment_source_id = f"{seed.key}-delayed-payment-{item}"
        pincode = BASE_PINCODES[(item + 2) % len(BASE_PINCODES)]
        total_paise = 150000 + (item * 25000)
        await insert_source_record(
            conn,
            seed=seed,
            raw_id=order_raw_id,
            source="shopify",
            resource="orders",
            source_record_id=order_source_id,
            payload={},
        )
        await insert_source_record(
            conn,
            seed=seed,
            raw_id=shipment_raw_id,
            source="shiprocket",
            resource="shipments",
            source_record_id=shipment_source_id,
            payload={},
        )
        await insert_source_record(
            conn,
            seed=seed,
            raw_id=payment_raw_id,
            source="razorpay",
            resource="payments",
            source_record_id=payment_source_id,
            payload={},
        )
        await upsert_order(
            conn, seed, order_id, order_source_id, order_raw_id, "prepaid", total_paise, pincode
        )
        await upsert_shipment(
            conn,
            seed,
            shipment_id,
            shipment_source_id,
            shipment_raw_id,
            "in_transit",
            13000 + (item * 1000),
            pincode,
            picked_up_days=6 + item,
        )
        await upsert_payment(conn, seed, payment_id, payment_source_id, payment_raw_id, total_paise)
        await upsert_link(conn, seed, link_id, order_id, shipment_id, payment_id)


async def seed_refund_shipping_mismatch(conn, seed: MerchantSeed) -> None:
    for item in range(1, seed.refund_mismatches + 1):
        index = 6200 + item
        order_id = _uuid("ae", seed, index)
        shipment_id = _uuid("af", seed, index)
        payment_id = _uuid("b0", seed, index)
        refund_id = _uuid("b1", seed, index)
        link_id = _uuid("b2", seed, index)
        order_raw_id = _uuid("b3", seed, index)
        shipment_raw_id = _uuid("b4", seed, index)
        payment_raw_id = _uuid("b5", seed, index)
        refund_raw_id = _uuid("b6", seed, index)
        order_source_id = f"{seed.key}-refund-order-{item}"
        shipment_source_id = f"{seed.key}-refund-shipment-{item}"
        payment_source_id = f"{seed.key}-refund-payment-{item}"
        refund_source_id = f"{seed.key}-refund-{item}"
        pincode = BASE_PINCODES[(item + 3) % len(BASE_PINCODES)]
        amount_paise = 190000 + (item * 30000)
        freight_paise = 16000 + (item * 1500)
        await insert_source_record(
            conn,
            seed=seed,
            raw_id=order_raw_id,
            source="shopify",
            resource="orders",
            source_record_id=order_source_id,
            payload={},
        )
        await insert_source_record(
            conn,
            seed=seed,
            raw_id=shipment_raw_id,
            source="shiprocket",
            resource="shipments",
            source_record_id=shipment_source_id,
            payload={},
        )
        await insert_source_record(
            conn,
            seed=seed,
            raw_id=payment_raw_id,
            source="razorpay",
            resource="payments",
            source_record_id=payment_source_id,
            payload={},
        )
        await insert_source_record(
            conn,
            seed=seed,
            raw_id=refund_raw_id,
            source="razorpay",
            resource="refunds",
            source_record_id=refund_source_id,
            payload={},
        )
        await upsert_order(
            conn, seed, order_id, order_source_id, order_raw_id, "prepaid", amount_paise, pincode
        )
        await upsert_shipment(
            conn,
            seed,
            shipment_id,
            shipment_source_id,
            shipment_raw_id,
            "in_transit",
            freight_paise,
            pincode,
            picked_up_days=4 + item,
        )
        await upsert_payment(
            conn, seed, payment_id, payment_source_id, payment_raw_id, amount_paise
        )
        await upsert_link(conn, seed, link_id, order_id, shipment_id, payment_id)
        await conn.execute(
            text(
                """
                INSERT INTO refunds (
                    merchant_id, id, source, source_record_id, raw_record_id, payment_id,
                    status, amount_paise, reason, processed_at, extras, synced_at, created_at, updated_at
                )
                VALUES (
                    :merchant_id, :id, 'razorpay', :source_id, :raw_id, :payment_id,
                    'processed', :amount_paise, 'goodwill', now() - interval '1 day',
                    '{}'::jsonb, now(), now(), now()
                )
                ON CONFLICT (merchant_id, source, source_record_id)
                DO UPDATE SET processed_at = EXCLUDED.processed_at,
                              amount_paise = EXCLUDED.amount_paise,
                              updated_at = now()
                """
            ),
            {
                "merchant_id": str(seed.merchant_id),
                "id": str(refund_id),
                "source_id": refund_source_id,
                "raw_id": str(refund_raw_id),
                "payment_id": str(payment_id),
                "amount_paise": amount_paise,
            },
        )


async def insert_source_record(
    conn,
    *,
    seed: MerchantSeed,
    raw_id: UUID,
    source: str,
    resource: str,
    source_record_id: str,
    payload: dict,
) -> None:
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


async def upsert_order(
    conn,
    seed: MerchantSeed,
    order_id: UUID,
    source_id: str,
    raw_id: UUID,
    payment_method: str,
    total_paise: int,
    pincode: str,
) -> None:
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
                          shipping_pincode = EXCLUDED.shipping_pincode,
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


async def upsert_shipment(
    conn,
    seed: MerchantSeed,
    shipment_id: UUID,
    source_id: str,
    raw_id: UUID,
    status: str,
    freight_paise: int,
    pincode: str,
    *,
    picked_up_days: int,
    courier_id: str = "xb",
    courier_name: str = "Xpressbees",
    pickup_pincode: str = "560001",
    weight_grams: int = 500,
) -> None:
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
                :courier_id, :courier_name, :status, :freight_paise, :weight_grams,
                :pickup_pincode, :pincode, now() - (:picked_up_days * interval '1 day'),
                now() - interval '3 days',
                CASE WHEN :status LIKE 'rto%' THEN now() - interval '1 day' ELSE NULL END,
                '{}'::jsonb, now(), now(), now()
            )
            ON CONFLICT (merchant_id, source, source_record_id)
            DO UPDATE SET status = EXCLUDED.status,
                          freight_paise = EXCLUDED.freight_paise,
                          courier_id = EXCLUDED.courier_id,
                          courier_name = EXCLUDED.courier_name,
                          pickup_pincode = EXCLUDED.pickup_pincode,
                          delivery_pincode = EXCLUDED.delivery_pincode,
                          weight_grams = EXCLUDED.weight_grams,
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
            "courier_id": courier_id,
            "courier_name": courier_name,
            "pickup_pincode": pickup_pincode,
            "weight_grams": weight_grams,
        },
    )


async def upsert_payment(
    conn,
    seed: MerchantSeed,
    payment_id: UUID,
    source_id: str,
    raw_id: UUID,
    amount_paise: int,
    *,
    method: str = "upi",
) -> None:
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
                'captured', :method, :amount_paise, 0, 0, :amount_paise,
                'INR', now() - interval '4 days', '{}'::jsonb, now(), now(), now()
            )
            ON CONFLICT (merchant_id, source, source_record_id)
            DO UPDATE SET method = EXCLUDED.method,
                          amount_paise = EXCLUDED.amount_paise,
                          updated_at = now()
            """
        ),
        {
            "merchant_id": str(seed.merchant_id),
            "id": str(payment_id),
            "source_id": source_id,
            "raw_id": str(raw_id),
            "amount_paise": amount_paise,
            "method": method,
        },
    )


async def upsert_link(
    conn,
    seed: MerchantSeed,
    link_id: UUID,
    order_id: UUID,
    shipment_id: UUID,
    payment_id: UUID | None,
) -> None:
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
    if 0 <= index <= 999:
        return UUID(f"{prefix}000000-0000-0000-0000-00000000{suffix}{index:03d}")
    return uuid5(NAMESPACE_URL, f"drishti-demo:{prefix}:{seed.key}:{index}")


if __name__ == "__main__":
    asyncio.run(main())
