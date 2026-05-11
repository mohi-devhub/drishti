"""init sync runs"""

from alembic import op

revision = "0003_init_sync_runs"
down_revision = "0002_init_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE sync_runs (
            merchant_id uuid NOT NULL REFERENCES merchants(id),
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            connection_id uuid REFERENCES connections(id),
            source text NOT NULL,
            resource text NOT NULL,
            trigger text NOT NULL CHECK (trigger IN ('cron','webhook','manual','backfill')),
            status text NOT NULL CHECK (status IN ('running','completed','failed','partial')),
            cursor_before jsonb,
            cursor_after jsonb,
            records_fetched int NOT NULL DEFAULT 0,
            records_normalized int NOT NULL DEFAULT 0,
            api_calls int NOT NULL DEFAULT 0,
            api_throttle_events int NOT NULL DEFAULT 0,
            queue_wait_ms int,
            error jsonb,
            started_at timestamptz,
            finished_at timestamptz
        );
        CREATE INDEX sync_runs_merchant_started_idx ON sync_runs (merchant_id, started_at DESC);
        CREATE INDEX sync_runs_merchant_source_resource_started_idx
            ON sync_runs (merchant_id, source, resource, started_at DESC);
        CREATE INDEX sync_runs_merchant_problem_idx ON sync_runs (merchant_id, status)
            WHERE status IN ('failed','partial');
        ALTER TABLE sync_runs ENABLE ROW LEVEL SECURITY;
        CREATE POLICY merchant_isolation ON sync_runs
            USING (merchant_id = current_setting('app.current_merchant_id', true)::uuid)
            WITH CHECK (merchant_id = current_setting('app.current_merchant_id', true)::uuid);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sync_runs CASCADE")
