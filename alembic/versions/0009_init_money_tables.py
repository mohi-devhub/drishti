"""init money tables"""

from alembic import op

revision = "0009_init_money_tables"
down_revision = "0008_init_logistics_tables"
branch_labels = None
depends_on = None

RLS = """
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
CREATE POLICY merchant_isolation ON {table}
    USING (merchant_id = current_setting('app.current_merchant_id', true)::uuid)
    WITH CHECK (merchant_id = current_setting('app.current_merchant_id', true)::uuid);
"""


def execute_statements(sql: str) -> None:
    for statement in (part.strip() for part in sql.split(";")):
        if statement:
            op.execute(statement)


def upgrade() -> None:
    execute_statements(
        """
        CREATE TABLE payments (
            merchant_id uuid NOT NULL REFERENCES merchants(id),
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            source text NOT NULL,
            source_record_id text NOT NULL,
            raw_record_id uuid NOT NULL REFERENCES source_records(id),
            sync_run_id uuid REFERENCES sync_runs(id),
            status text NOT NULL,
            method text,
            amount_paise bigint NOT NULL,
            fee_paise bigint,
            tax_paise bigint,
            net_paise bigint,
            currency text NOT NULL DEFAULT 'INR',
            captured_at timestamptz,
            extras jsonb NOT NULL DEFAULT '{}'::jsonb,
            synced_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (merchant_id, source, source_record_id)
        );
        CREATE INDEX payments_merchant_status_captured_idx
            ON payments (merchant_id, status, captured_at DESC);
        CREATE INDEX payments_merchant_method_captured_idx
            ON payments (merchant_id, method, captured_at DESC);

        CREATE TABLE refunds (
            merchant_id uuid NOT NULL REFERENCES merchants(id),
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            source text NOT NULL,
            source_record_id text NOT NULL,
            raw_record_id uuid NOT NULL REFERENCES source_records(id),
            sync_run_id uuid REFERENCES sync_runs(id),
            payment_id uuid NOT NULL REFERENCES payments(id),
            status text NOT NULL,
            amount_paise bigint NOT NULL,
            reason text,
            processed_at timestamptz,
            extras jsonb NOT NULL DEFAULT '{}'::jsonb,
            synced_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (merchant_id, source, source_record_id)
        );
        CREATE INDEX refunds_merchant_payment_idx ON refunds (merchant_id, payment_id);
        CREATE INDEX refunds_merchant_processed_idx ON refunds (merchant_id, processed_at DESC);

        CREATE TABLE settlements (
            merchant_id uuid NOT NULL REFERENCES merchants(id),
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            source text NOT NULL,
            source_record_id text NOT NULL,
            raw_record_id uuid NOT NULL REFERENCES source_records(id),
            sync_run_id uuid REFERENCES sync_runs(id),
            status text NOT NULL,
            amount_paise bigint NOT NULL,
            fees_paise bigint,
            tax_paise bigint,
            utr text,
            settled_at timestamptz,
            extras jsonb NOT NULL DEFAULT '{}'::jsonb,
            synced_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (merchant_id, source, source_record_id)
        );
        CREATE INDEX settlements_merchant_settled_idx ON settlements (merchant_id, settled_at DESC);
        """
    )
    for table in ("payments", "refunds", "settlements"):
        execute_statements(RLS.format(table=table))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS settlements CASCADE")
    op.execute("DROP TABLE IF EXISTS refunds CASCADE")
    op.execute("DROP TABLE IF EXISTS payments CASCADE")
