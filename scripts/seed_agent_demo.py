from __future__ import annotations

import argparse
import asyncio
from uuid import UUID

from sqlalchemy import text

from drishti.agents.rto_shipping_margin.agent import run_worker
from drishti.config import get_settings
from drishti.db.session import create_engine, set_merchant_context

MERCHANT_C = UUID("00000000-0000-0000-0000-00000000000c")


async def seed(*, run_agent: bool) -> None:
    engine = create_engine(get_settings())
    async with engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_merchant_id', :merchant_id, true)"),
            {"merchant_id": str(MERCHANT_C)},
        )
        await conn.execute(
            text(
                """
                INSERT INTO merchants (id, clerk_org_id, name, subdomain, time_zone, created_at, updated_at)
                VALUES (:merchant_id, 'org_demo_merchant_c', 'Demo Merchant C', 'merchant-c',
                        'Asia/Kolkata', now(), now())
                ON CONFLICT (id) DO UPDATE SET updated_at = now()
                """
            ),
            {"merchant_id": str(MERCHANT_C)},
        )
        for index in range(1, 6):
            order_source_id = f"agent-demo-order-{index}"
            shipment_source_id = f"agent-demo-shipment-{index}"
            order_raw_id = UUID(f"10000000-0000-0000-0000-00000000c{index:03d}")
            shipment_raw_id = UUID(f"11000000-0000-0000-0000-00000000c{index:03d}")
            order_id = UUID(f"40000000-0000-0000-0000-00000000c{index:03d}")
            shipment_id = UUID(f"50000000-0000-0000-0000-00000000c{index:03d}")
            link_id = UUID(f"60000000-0000-0000-0000-00000000c{index:03d}")
            await conn.execute(
                text(
                    """
                    INSERT INTO source_records (
                        merchant_id, id, source, resource, source_record_id, endpoint,
                        fetched_at, payload, payload_hash, created_at
                    )
                    VALUES
                        (:merchant_id, :order_raw_id, 'shopify', 'orders', :order_source_id,
                         'seed://agent-demo/orders', now(), '{}'::jsonb, :order_hash, now()),
                        (:merchant_id, :shipment_raw_id, 'shiprocket', 'shipments', :shipment_source_id,
                         'seed://agent-demo/shipments', now(), '{}'::jsonb, :shipment_hash, now())
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {
                    "merchant_id": str(MERCHANT_C),
                    "order_raw_id": str(order_raw_id),
                    "shipment_raw_id": str(shipment_raw_id),
                    "order_source_id": order_source_id,
                    "shipment_source_id": shipment_source_id,
                    "order_hash": f"agent-demo-order-hash-{index}",
                    "shipment_hash": f"agent-demo-shipment-hash-{index}",
                },
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
                        :merchant_id, :order_id, 'shopify', :order_source_id, :order_raw_id,
                        now() - interval '5 days', 'confirmed', 'cod', 45000, 42000,
                        3000, 0, 0, 'INR', '110001', 'IN', 1,
                        jsonb_build_object('name', CAST(:order_name AS text)), now(), now(), now()
                    )
                    ON CONFLICT (merchant_id, source, source_record_id)
                    DO UPDATE SET total_paise = EXCLUDED.total_paise,
                                  payment_method = EXCLUDED.payment_method,
                                  updated_at = now()
                    """
                ),
                {
                    "merchant_id": str(MERCHANT_C),
                    "order_id": str(order_id),
                    "order_source_id": order_source_id,
                    "order_raw_id": str(order_raw_id),
                    "order_name": f"#AGENT-C-{index}",
                },
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO shipments (
                        merchant_id, id, source, source_record_id, raw_record_id,
                        awb_code, courier_id, courier_name, status, freight_paise,
                        weight_grams, pickup_pincode, delivery_pincode, picked_up_at,
                        rto_initiated_at, expected_delivery_at, extras, synced_at, created_at, updated_at
                    )
                    VALUES (
                        :merchant_id, :shipment_id, 'shiprocket', :shipment_source_id, :shipment_raw_id,
                        :awb_code, 'xb', 'Xpressbees', 'rto_initiated', 25000,
                        500, '560001', '110001', now() - interval '4 days',
                        now() - interval '1 day', now() - interval '2 days',
                        jsonb_build_object('order_id', CAST(:order_name AS text)), now(), now(), now()
                    )
                    ON CONFLICT (merchant_id, source, source_record_id)
                    DO UPDATE SET status = EXCLUDED.status,
                                  freight_paise = EXCLUDED.freight_paise,
                                  updated_at = now()
                    """
                ),
                {
                    "merchant_id": str(MERCHANT_C),
                    "shipment_id": str(shipment_id),
                    "shipment_source_id": shipment_source_id,
                    "shipment_raw_id": str(shipment_raw_id),
                    "awb_code": f"AWBAGENTC{index:03d}",
                    "order_name": f"#AGENT-C-{index}",
                },
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO order_links (
                        merchant_id, id, order_id, shipment_id, linkage_method,
                        confidence, created_at, updated_at
                    )
                    VALUES (
                        :merchant_id, :link_id, :order_id, :shipment_id,
                        'order_id_match', 1.0, now(), now()
                    )
                    ON CONFLICT (merchant_id, order_id)
                    DO UPDATE SET shipment_id = EXCLUDED.shipment_id, updated_at = now()
                    """
                ),
                {
                    "merchant_id": str(MERCHANT_C),
                    "link_id": str(link_id),
                    "order_id": str(order_id),
                    "shipment_id": str(shipment_id),
                },
            )
    if run_agent:
        async with engine.begin() as conn:
            await set_merchant_context(conn, MERCHANT_C)
            result = await run_worker(conn, merchant_id=MERCHANT_C, trigger="manual")
            print(result)
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-agent", action="store_true")
    args = parser.parse_args()
    asyncio.run(seed(run_agent=args.run_agent))


if __name__ == "__main__":
    main()
