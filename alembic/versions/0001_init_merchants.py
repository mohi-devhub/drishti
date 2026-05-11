"""init merchants"""

from alembic import op

revision = "0001_init_merchants"
down_revision = None
branch_labels = None
depends_on = None


def execute_statements(sql: str) -> None:
    for statement in (part.strip() for part in sql.split(";")):
        if statement:
            op.execute(statement)


def upgrade() -> None:
    execute_statements(
        """
        CREATE EXTENSION IF NOT EXISTS "pgcrypto";
        CREATE TABLE merchants (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clerk_org_id text UNIQUE NOT NULL,
            name text NOT NULL,
            subdomain text UNIQUE,
            time_zone text NOT NULL DEFAULT 'Asia/Kolkata',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
        ALTER TABLE merchants ENABLE ROW LEVEL SECURITY;
        CREATE POLICY merchant_isolation ON merchants
            USING (id = current_setting('app.current_merchant_id', true)::uuid)
            WITH CHECK (id = current_setting('app.current_merchant_id', true)::uuid);
        INSERT INTO merchants (id, clerk_org_id, name, subdomain)
        VALUES
            ('00000000-0000-0000-0000-00000000000a', 'merchant_a', 'Merchant A', 'merchant-a'),
            ('00000000-0000-0000-0000-00000000000b', 'merchant_b', 'Merchant B', 'merchant-b'),
            ('00000000-0000-0000-0000-00000000000c', 'merchant_c', 'Merchant C', 'merchant-c')
        ON CONFLICT (id) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS merchants CASCADE")
