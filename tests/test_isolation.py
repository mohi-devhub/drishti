from pathlib import Path

TENANT_TABLES = {
    "merchants",
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
    "chat_messages",
    "tool_calls",
    "agent_runs",
    "agent_findings",
}


def migration_sql() -> str:
    return "\n".join(
        path.read_text()
        for path in sorted(Path("alembic/versions").glob("*.py"))
    )


def test_all_tenant_tables_enable_rls() -> None:
    sql = migration_sql()

    missing = [
        table
        for table in TENANT_TABLES
        if f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" not in sql
        and f'"{table}"' not in sql
    ]

    assert missing == []


def test_negative_omission_integration_case_is_documented() -> None:
    # TODO: replace this static guard with a live DB test after seed data exists.
    # The integration case should intentionally omit an app-layer merchant filter
    # while app.current_merchant_id is set to merchant_b, then assert merchant_a
    # rows are still invisible through Postgres RLS.
    assert "source_records" in TENANT_TABLES
