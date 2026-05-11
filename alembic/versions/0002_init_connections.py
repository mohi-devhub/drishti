"""init connections"""

from alembic import op

revision = "0002_init_connections"
down_revision = "0001_init_merchants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE connections (
            merchant_id uuid NOT NULL REFERENCES merchants(id),
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            source text NOT NULL CHECK (source IN ('shopify','shiprocket','razorpay')),
            status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','revoked','error')),
            auth_payload jsonb NOT NULL,
            cursors jsonb NOT NULL DEFAULT '{}'::jsonb,
            last_synced_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (merchant_id, source)
        );
        CREATE INDEX connections_merchant_status_idx ON connections (merchant_id, status);
        ALTER TABLE connections ENABLE ROW LEVEL SECURITY;
        CREATE POLICY merchant_isolation ON connections
            USING (merchant_id = current_setting('app.current_merchant_id', true)::uuid)
            WITH CHECK (merchant_id = current_setting('app.current_merchant_id', true)::uuid);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS connections CASCADE")
