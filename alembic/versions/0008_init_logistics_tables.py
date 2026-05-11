"""init logistics tables"""

from alembic import op

revision = "0008_init_logistics_tables"
down_revision = "0007_init_order_line_items"
branch_labels = None
depends_on = None


def execute_statements(sql: str) -> None:
    for statement in (part.strip() for part in sql.split(";")):
        if statement:
            op.execute(statement)


def upgrade() -> None:
    execute_statements(
        """
        CREATE TABLE shipments (
            merchant_id uuid NOT NULL REFERENCES merchants(id),
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            source text NOT NULL,
            source_record_id text NOT NULL,
            raw_record_id uuid NOT NULL REFERENCES source_records(id),
            sync_run_id uuid REFERENCES sync_runs(id),
            awb_code text,
            courier_id text,
            courier_name text,
            status text NOT NULL,
            freight_paise bigint,
            weight_grams int,
            pickup_pincode text,
            delivery_pincode text,
            picked_up_at timestamptz,
            delivered_at timestamptz,
            rto_initiated_at timestamptz,
            expected_delivery_at timestamptz,
            extras jsonb NOT NULL DEFAULT '{}'::jsonb,
            synced_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (merchant_id, source, source_record_id)
        );
        CREATE UNIQUE INDEX shipments_merchant_awb_idx ON shipments (merchant_id, awb_code)
            WHERE awb_code IS NOT NULL;
        CREATE INDEX shipments_merchant_status_idx ON shipments (merchant_id, status);
        CREATE INDEX shipments_merchant_courier_status_idx ON shipments (merchant_id, courier_id, status);
        CREATE INDEX shipments_merchant_delivery_status_idx
            ON shipments (merchant_id, delivery_pincode, status);
        CREATE INDEX shipments_merchant_expected_idx ON shipments (merchant_id, expected_delivery_at)
            WHERE status NOT IN ('delivered','cancelled');

        CREATE TABLE tracking_events (
            merchant_id uuid NOT NULL REFERENCES merchants(id),
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            shipment_id uuid NOT NULL REFERENCES shipments(id),
            raw_record_id uuid NOT NULL REFERENCES source_records(id),
            sync_run_id uuid REFERENCES sync_runs(id),
            event_status text NOT NULL,
            event_message text,
            location text,
            event_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX tracking_events_merchant_shipment_event_idx
            ON tracking_events (merchant_id, shipment_id, event_at DESC);

        ALTER TABLE shipments ENABLE ROW LEVEL SECURITY;
        CREATE POLICY merchant_isolation ON shipments
            USING (merchant_id = current_setting('app.current_merchant_id', true)::uuid)
            WITH CHECK (merchant_id = current_setting('app.current_merchant_id', true)::uuid);
        ALTER TABLE tracking_events ENABLE ROW LEVEL SECURITY;
        CREATE POLICY merchant_isolation ON tracking_events
            USING (merchant_id = current_setting('app.current_merchant_id', true)::uuid)
            WITH CHECK (merchant_id = current_setting('app.current_merchant_id', true)::uuid);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tracking_events CASCADE")
    op.execute("DROP TABLE IF EXISTS shipments CASCADE")
