"""init source records"""

from alembic import op

revision = "0004_init_source_records"
down_revision = "0003_init_sync_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE source_records (
            merchant_id uuid NOT NULL REFERENCES merchants(id),
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            sync_run_id uuid REFERENCES sync_runs(id),
            source text NOT NULL,
            resource text NOT NULL,
            source_record_id text NOT NULL,
            endpoint text NOT NULL,
            fetched_at timestamptz NOT NULL,
            payload jsonb NOT NULL,
            payload_hash text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (merchant_id, source, source_record_id, payload_hash)
        );
        CREATE INDEX source_records_merchant_source_record_fetched_idx
            ON source_records (merchant_id, source, source_record_id, fetched_at DESC);
        CREATE INDEX source_records_merchant_fetched_idx
            ON source_records (merchant_id, fetched_at DESC);
        CREATE INDEX source_records_merchant_source_resource_fetched_idx
            ON source_records (merchant_id, source, resource, fetched_at DESC);
        ALTER TABLE source_records ENABLE ROW LEVEL SECURITY;
        CREATE POLICY merchant_isolation ON source_records
            USING (merchant_id = current_setting('app.current_merchant_id', true)::uuid)
            WITH CHECK (merchant_id = current_setting('app.current_merchant_id', true)::uuid);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS source_records CASCADE")
