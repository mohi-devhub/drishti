"""allow queued agent runs"""

from alembic import op

revision = "0016_allow_queued_agent_runs"
down_revision = "0015_init_clerk_user_merchants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE agent_runs DROP CONSTRAINT IF EXISTS agent_runs_status_check")
    op.execute(
        """
        ALTER TABLE agent_runs
        ADD CONSTRAINT agent_runs_status_check
        CHECK (status IN ('queued','running','completed','failed','partial'))
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE agent_runs DROP CONSTRAINT IF EXISTS agent_runs_status_check")
    op.execute(
        """
        ALTER TABLE agent_runs
        ADD CONSTRAINT agent_runs_status_check
        CHECK (status IN ('running','completed','failed','partial'))
        """
    )
