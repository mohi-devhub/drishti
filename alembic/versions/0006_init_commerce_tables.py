"""init commerce tables"""

from alembic import op

revision = "0006_init_commerce_tables"
down_revision = "0005_init_webhook_deliveries"
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
        CREATE TABLE customers (
            merchant_id uuid NOT NULL REFERENCES merchants(id),
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            source text NOT NULL,
            source_record_id text NOT NULL,
            raw_record_id uuid NOT NULL REFERENCES source_records(id),
            sync_run_id uuid REFERENCES sync_runs(id),
            email text,
            phone text,
            first_name text,
            last_name text,
            total_spent_paise bigint,
            currency text NOT NULL DEFAULT 'INR',
            extras jsonb NOT NULL DEFAULT '{}'::jsonb,
            synced_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (merchant_id, source, source_record_id)
        );
        CREATE INDEX customers_merchant_email_idx ON customers (merchant_id, email)
            WHERE email IS NOT NULL;

        CREATE TABLE products (
            merchant_id uuid NOT NULL REFERENCES merchants(id),
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            source text NOT NULL,
            source_record_id text NOT NULL,
            raw_record_id uuid NOT NULL REFERENCES source_records(id),
            sync_run_id uuid REFERENCES sync_runs(id),
            title text NOT NULL,
            sku text,
            price_paise bigint,
            currency text NOT NULL DEFAULT 'INR',
            weight_grams int,
            extras jsonb NOT NULL DEFAULT '{}'::jsonb,
            synced_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (merchant_id, source, source_record_id)
        );
        CREATE INDEX products_merchant_sku_idx ON products (merchant_id, sku)
            WHERE sku IS NOT NULL;

        CREATE TABLE orders (
            merchant_id uuid NOT NULL REFERENCES merchants(id),
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            source text NOT NULL,
            source_record_id text NOT NULL,
            raw_record_id uuid NOT NULL REFERENCES source_records(id),
            sync_run_id uuid REFERENCES sync_runs(id),
            customer_id uuid REFERENCES customers(id),
            placed_at timestamptz NOT NULL,
            status text NOT NULL,
            payment_method text NOT NULL,
            total_paise bigint NOT NULL,
            subtotal_paise bigint,
            shipping_paise bigint,
            tax_paise bigint,
            discount_paise bigint,
            currency text NOT NULL DEFAULT 'INR',
            shipping_pincode text,
            shipping_country text NOT NULL DEFAULT 'IN',
            line_items_count int NOT NULL,
            extras jsonb NOT NULL DEFAULT '{}'::jsonb,
            synced_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (merchant_id, source, source_record_id)
        );
        CREATE INDEX orders_merchant_placed_idx ON orders (merchant_id, placed_at DESC);
        CREATE INDEX orders_merchant_status_idx ON orders (merchant_id, status);
        CREATE INDEX orders_merchant_payment_placed_idx
            ON orders (merchant_id, payment_method, placed_at DESC);
        CREATE INDEX orders_merchant_pincode_payment_idx
            ON orders (merchant_id, shipping_pincode, payment_method);
        """
    )
    for table in ("customers", "products", "orders"):
        execute_statements(RLS.format(table=table))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS orders CASCADE")
    op.execute("DROP TABLE IF EXISTS products CASCADE")
    op.execute("DROP TABLE IF EXISTS customers CASCADE")
