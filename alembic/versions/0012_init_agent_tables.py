"""init agent tables"""

from alembic import op

revision = "0012_init_agent_tables"
down_revision = "0011_init_chat_tables"
branch_labels = None
depends_on = None


def execute_statements(sql: str) -> None:
    for statement in (part.strip() for part in sql.split(";")):
        if statement:
            op.execute(statement)


def upgrade() -> None:
    execute_statements(
        """
        CREATE TABLE agent_runs (
            merchant_id uuid NOT NULL REFERENCES merchants(id),
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_name text NOT NULL DEFAULT 'rto_shipping_margin_worker',
            trigger text NOT NULL CHECK (trigger IN ('scheduled','manual','backfill')),
            status text NOT NULL CHECK (status IN ('running','completed','failed','partial')),
            duties_run text[],
            duties_skipped jsonb,
            input_snapshot jsonb NOT NULL,
            findings_count int NOT NULL DEFAULT 0,
            errors jsonb,
            started_at timestamptz,
            finished_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX agent_runs_merchant_started_idx ON agent_runs (merchant_id, started_at DESC);
        CREATE INDEX agent_runs_merchant_status_idx ON agent_runs (merchant_id, status);
        CREATE INDEX agent_runs_merchant_trigger_started_idx
            ON agent_runs (merchant_id, trigger, started_at DESC);

        CREATE TABLE agent_findings (
            merchant_id uuid NOT NULL REFERENCES merchants(id),
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id uuid NOT NULL REFERENCES agent_runs(id),
            duty text NOT NULL,
            finding_type text NOT NULL,
            severity text NOT NULL CHECK (severity IN ('low','medium','high')),
            confidence numeric(3,2) NOT NULL,
            evidence_row_ids text[] NOT NULL,
            estimated_saving_inr_low bigint,
            estimated_saving_inr_high bigint,
            narrative text,
            narrative_status text NOT NULL CHECK (narrative_status IN ('validated','degraded','failed')),
            proposed_action jsonb,
            citations jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX agent_findings_merchant_run_idx ON agent_findings (merchant_id, run_id);
        CREATE INDEX agent_findings_merchant_duty_severity_idx
            ON agent_findings (merchant_id, duty, severity);
        CREATE INDEX agent_findings_merchant_created_idx
            ON agent_findings (merchant_id, created_at DESC);

        ALTER TABLE agent_runs ENABLE ROW LEVEL SECURITY;
        CREATE POLICY merchant_isolation ON agent_runs
            USING (merchant_id = current_setting('app.current_merchant_id', true)::uuid)
            WITH CHECK (merchant_id = current_setting('app.current_merchant_id', true)::uuid);
        ALTER TABLE agent_findings ENABLE ROW LEVEL SECURITY;
        CREATE POLICY merchant_isolation ON agent_findings
            USING (merchant_id = current_setting('app.current_merchant_id', true)::uuid)
            WITH CHECK (merchant_id = current_setting('app.current_merchant_id', true)::uuid);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_findings CASCADE")
    op.execute("DROP TABLE IF EXISTS agent_runs CASCADE")
