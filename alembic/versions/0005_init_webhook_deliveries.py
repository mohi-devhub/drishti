"""init webhook deliveries"""

from alembic import op

revision = "0005_init_webhook_deliveries"
down_revision = "0004_init_source_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE webhook_deliveries (
            merchant_id uuid NOT NULL REFERENCES merchants(id),
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            source text NOT NULL,
            external_id text NOT NULL,
            topic text NOT NULL,
            received_at timestamptz NOT NULL,
            processed_at timestamptz,
            payload_hash text NOT NULL,
            UNIQUE (merchant_id, source, external_id)
        );
        ALTER TABLE webhook_deliveries ENABLE ROW LEVEL SECURITY;
        CREATE POLICY merchant_isolation ON webhook_deliveries
            USING (merchant_id = current_setting('app.current_merchant_id', true)::uuid)
            WITH CHECK (merchant_id = current_setting('app.current_merchant_id', true)::uuid);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS webhook_deliveries CASCADE")
