"""init chat tables"""

from alembic import op

revision = "0011_init_chat_tables"
down_revision = "0010_init_order_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE chat_sessions (
            merchant_id uuid NOT NULL REFERENCES merchants(id),
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clerk_user_id text NOT NULL,
            title text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX chat_sessions_merchant_user_updated_idx
            ON chat_sessions (merchant_id, clerk_user_id, updated_at DESC);

        CREATE TABLE tool_calls (
            merchant_id uuid NOT NULL REFERENCES merchants(id),
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            caller text NOT NULL CHECK (caller IN ('chat','agent')),
            caller_id uuid,
            tool_name text NOT NULL,
            args jsonb NOT NULL,
            result jsonb,
            result_id text,
            validation_status text CHECK (validation_status IN ('pending','passed','retried','redacted')),
            validation_failures jsonb,
            latency_ms int,
            started_at timestamptz,
            finished_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX tool_calls_merchant_started_idx ON tool_calls (merchant_id, started_at DESC);
        CREATE INDEX tool_calls_merchant_caller_idx ON tool_calls (merchant_id, caller, caller_id);
        CREATE INDEX tool_calls_merchant_validation_problem_idx
            ON tool_calls (merchant_id, validation_status)
            WHERE validation_status IN ('retried','redacted');

        CREATE TABLE chat_messages (
            merchant_id uuid NOT NULL REFERENCES merchants(id),
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id uuid NOT NULL REFERENCES chat_sessions(id),
            role text NOT NULL CHECK (role IN ('user','assistant','tool')),
            content text NOT NULL,
            tool_call_id uuid REFERENCES tool_calls(id),
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX chat_messages_merchant_session_created_idx
            ON chat_messages (merchant_id, session_id, created_at);

        ALTER TABLE chat_sessions ENABLE ROW LEVEL SECURITY;
        CREATE POLICY merchant_isolation ON chat_sessions
            USING (merchant_id = current_setting('app.current_merchant_id', true)::uuid)
            WITH CHECK (merchant_id = current_setting('app.current_merchant_id', true)::uuid);
        ALTER TABLE tool_calls ENABLE ROW LEVEL SECURITY;
        CREATE POLICY merchant_isolation ON tool_calls
            USING (merchant_id = current_setting('app.current_merchant_id', true)::uuid)
            WITH CHECK (merchant_id = current_setting('app.current_merchant_id', true)::uuid);
        ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;
        CREATE POLICY merchant_isolation ON chat_messages
            USING (merchant_id = current_setting('app.current_merchant_id', true)::uuid)
            WITH CHECK (merchant_id = current_setting('app.current_merchant_id', true)::uuid);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chat_messages CASCADE")
    op.execute("DROP TABLE IF EXISTS tool_calls CASCADE")
    op.execute("DROP TABLE IF EXISTS chat_sessions CASCADE")
