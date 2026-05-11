"""init order links"""

from alembic import op

revision = "0010_init_order_links"
down_revision = "0009_init_money_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE order_links (
            merchant_id uuid NOT NULL REFERENCES merchants(id),
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            order_id uuid NOT NULL REFERENCES orders(id),
            shipment_id uuid REFERENCES shipments(id),
            payment_id uuid REFERENCES payments(id),
            linkage_method text NOT NULL CHECK (linkage_method IN ('order_id_match','metadata_match','manual')),
            confidence numeric(3,2) NOT NULL DEFAULT 1.00,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (merchant_id, order_id)
        );
        CREATE INDEX order_links_merchant_shipment_idx ON order_links (merchant_id, shipment_id)
            WHERE shipment_id IS NOT NULL;
        CREATE INDEX order_links_merchant_payment_idx ON order_links (merchant_id, payment_id)
            WHERE payment_id IS NOT NULL;
        ALTER TABLE order_links ENABLE ROW LEVEL SECURITY;
        CREATE POLICY merchant_isolation ON order_links
            USING (merchant_id = current_setting('app.current_merchant_id', true)::uuid)
            WITH CHECK (merchant_id = current_setting('app.current_merchant_id', true)::uuid);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS order_links CASCADE")
