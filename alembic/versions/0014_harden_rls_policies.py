"""harden rls policies"""

from alembic import op

revision = "0014_harden_rls_policies"
down_revision = "0013_init_immutability_triggers"
branch_labels = None
depends_on = None

MERCHANT_TABLES = (
    "connections",
    "sync_runs",
    "source_records",
    "webhook_deliveries",
    "customers",
    "products",
    "orders",
    "order_line_items",
    "shipments",
    "tracking_events",
    "payments",
    "refunds",
    "settlements",
    "order_links",
    "chat_sessions",
    "tool_calls",
    "chat_messages",
    "agent_runs",
    "agent_findings",
)


def upgrade() -> None:
    op.execute(
        """
        ALTER FUNCTION public.reject_source_record_mutation()
        SET search_path = ''
        """
    )
    op.execute(
        """
        CREATE POLICY deny_all ON alembic_version
            USING (false)
            WITH CHECK (false)
        """
    )
    op.execute("DROP POLICY merchant_isolation ON merchants")
    op.execute(
        """
        CREATE POLICY merchant_isolation ON merchants
            USING (id = (select current_setting('app.current_merchant_id', true)::uuid))
            WITH CHECK (id = (select current_setting('app.current_merchant_id', true)::uuid))
        """
    )
    for table in MERCHANT_TABLES:
        op.execute(f"DROP POLICY merchant_isolation ON {table}")
        op.execute(
            f"""
            CREATE POLICY merchant_isolation ON {table}
                USING (
                    merchant_id = (select current_setting('app.current_merchant_id', true)::uuid)
                )
                WITH CHECK (
                    merchant_id = (select current_setting('app.current_merchant_id', true)::uuid)
                )
            """
        )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS deny_all ON alembic_version")
    op.execute("DROP POLICY merchant_isolation ON merchants")
    op.execute(
        """
        CREATE POLICY merchant_isolation ON merchants
            USING (id = current_setting('app.current_merchant_id', true)::uuid)
            WITH CHECK (id = current_setting('app.current_merchant_id', true)::uuid)
        """
    )
    for table in MERCHANT_TABLES:
        op.execute(f"DROP POLICY merchant_isolation ON {table}")
        op.execute(
            f"""
            CREATE POLICY merchant_isolation ON {table}
                USING (merchant_id = current_setting('app.current_merchant_id', true)::uuid)
                WITH CHECK (merchant_id = current_setting('app.current_merchant_id', true)::uuid)
            """
        )
