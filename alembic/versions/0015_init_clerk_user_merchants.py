"""init clerk user merchant mappings"""

from alembic import op

revision = "0015_init_clerk_user_merchants"
down_revision = "0014_harden_rls_policies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clerk_user_merchants (
            merchant_id uuid NOT NULL REFERENCES merchants(id),
            clerk_user_id text NOT NULL,
            role text NOT NULL DEFAULT 'member',
            status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','revoked')),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (merchant_id, clerk_user_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS clerk_user_merchants_user_idx
            ON clerk_user_merchants (clerk_user_id, status);
        """
    )
    op.execute(
        """
        ALTER TABLE clerk_user_merchants ENABLE ROW LEVEL SECURITY;
        """
    )
    op.execute("DROP POLICY IF EXISTS merchant_isolation ON clerk_user_merchants")
    op.execute(
        """
        CREATE POLICY merchant_isolation ON clerk_user_merchants
            USING (
                merchant_id = (select current_setting('app.current_merchant_id', true)::uuid)
            )
            WITH CHECK (
                merchant_id = (select current_setting('app.current_merchant_id', true)::uuid)
            );
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION resolve_merchant_id_for_clerk(
            p_clerk_user_id text,
            p_clerk_org_id text
        )
        RETURNS uuid
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        STABLE
        AS $$
            SELECT COALESCE(
                (
                    SELECT id
                    FROM merchants
                    WHERE clerk_org_id = p_clerk_org_id
                    LIMIT 1
                ),
                (
                    SELECT merchant_id
                    FROM clerk_user_merchants
                    WHERE clerk_user_id = p_clerk_user_id
                      AND status = 'active'
                    ORDER BY created_at ASC
                    LIMIT 1
                )
            )
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION resolve_shopify_connection_for_webhook(
            p_shop_domain text
        )
        RETURNS TABLE (
            id uuid,
            merchant_id uuid,
            source text,
            auth_payload jsonb,
            cursors jsonb
        )
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        STABLE
        AS $$
            SELECT c.id, c.merchant_id, c.source, c.auth_payload, c.cursors
            FROM connections c
            WHERE c.source = 'shopify'
              AND c.status = 'active'
              AND (
                lower(c.auth_payload->>'shop') = p_shop_domain
                OR lower(c.auth_payload->>'shop_domain') = p_shop_domain
                OR lower(c.auth_payload->>'myshopify_domain') = p_shop_domain
              )
            LIMIT 1
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS resolve_shopify_connection_for_webhook(text)")
    op.execute("DROP FUNCTION IF EXISTS resolve_merchant_id_for_clerk(text, text)")
    op.execute("DROP TABLE IF EXISTS clerk_user_merchants CASCADE")
