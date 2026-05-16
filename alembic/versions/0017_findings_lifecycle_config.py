"""add finding lifecycle and duty config"""

from alembic import op

revision = "0017_findings_lifecycle_config"
down_revision = "0016_allow_queued_agent_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE agent_runs DROP CONSTRAINT IF EXISTS agent_runs_status_check
        """
    )
    op.execute(
        """
        ALTER TABLE agent_runs
        ADD CONSTRAINT agent_runs_status_check
        CHECK (status IN ('queued','running','completed','failed','partial','cancelled'))
        """
    )
    op.execute(
        """
        ALTER TABLE agent_findings
        ADD COLUMN IF NOT EXISTS lifecycle_status text NOT NULL DEFAULT 'open'
        CHECK (lifecycle_status IN ('open','acknowledged','actioned','dismissed'))
        """
    )
    op.execute("ALTER TABLE agent_findings ADD COLUMN IF NOT EXISTS fingerprint text")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS agent_findings_merchant_lifecycle_idx
            ON agent_findings (merchant_id, lifecycle_status, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS agent_runs_merchant_agent_created_idx
            ON agent_runs (merchant_id, agent_name, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS agent_findings_merchant_run_created_idx
            ON agent_findings (merchant_id, run_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS agent_findings_merchant_fingerprint_idx
            ON agent_findings (merchant_id, fingerprint)
            WHERE fingerprint IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_duty_configs (
            merchant_id uuid NOT NULL REFERENCES merchants(id),
            duty text NOT NULL,
            enabled boolean NOT NULL DEFAULT true,
            config jsonb NOT NULL DEFAULT '{}'::jsonb,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (merchant_id, duty)
        )
        """
    )
    op.execute("ALTER TABLE agent_duty_configs ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS merchant_isolation ON agent_duty_configs")
    op.execute(
        """
        CREATE POLICY merchant_isolation ON agent_duty_configs
            USING (merchant_id = current_setting('app.current_merchant_id', true)::uuid)
            WITH CHECK (merchant_id = current_setting('app.current_merchant_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_duty_configs CASCADE")
    op.execute("DROP INDEX IF EXISTS agent_findings_merchant_fingerprint_idx")
    op.execute("DROP INDEX IF EXISTS agent_findings_merchant_run_created_idx")
    op.execute("DROP INDEX IF EXISTS agent_runs_merchant_agent_created_idx")
    op.execute("DROP INDEX IF EXISTS agent_findings_merchant_lifecycle_idx")
    op.execute("ALTER TABLE agent_findings DROP COLUMN IF EXISTS fingerprint")
    op.execute("ALTER TABLE agent_findings DROP COLUMN IF EXISTS lifecycle_status")
    op.execute("ALTER TABLE agent_runs DROP CONSTRAINT IF EXISTS agent_runs_status_check")
    op.execute(
        """
        ALTER TABLE agent_runs
        ADD CONSTRAINT agent_runs_status_check
        CHECK (status IN ('queued','running','completed','failed','partial'))
        """
    )
