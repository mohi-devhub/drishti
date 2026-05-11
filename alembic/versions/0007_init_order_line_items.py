"""init order line items"""

from alembic import op

revision = "0007_init_order_line_items"
down_revision = "0006_init_commerce_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE order_line_items (
            merchant_id uuid NOT NULL REFERENCES merchants(id),
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            order_id uuid NOT NULL REFERENCES orders(id),
            product_id uuid REFERENCES products(id),
            source_record_id text,
            raw_record_id uuid NOT NULL REFERENCES source_records(id),
            quantity int NOT NULL,
            unit_price_paise bigint NOT NULL,
            total_paise bigint NOT NULL,
            extras jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX order_line_items_merchant_order_idx ON order_line_items (merchant_id, order_id);
        CREATE INDEX order_line_items_merchant_product_idx ON order_line_items (merchant_id, product_id)
            WHERE product_id IS NOT NULL;
        ALTER TABLE order_line_items ENABLE ROW LEVEL SECURITY;
        CREATE POLICY merchant_isolation ON order_line_items
            USING (merchant_id = current_setting('app.current_merchant_id', true)::uuid)
            WITH CHECK (merchant_id = current_setting('app.current_merchant_id', true)::uuid);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS order_line_items CASCADE")
