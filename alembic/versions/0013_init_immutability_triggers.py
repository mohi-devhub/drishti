"""init immutability triggers"""

from alembic import op

revision = "0013_init_immutability_triggers"
down_revision = "0012_init_agent_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_source_record_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'source_records are append-only';
        END;
        $$;

        CREATE TRIGGER source_records_no_update
            BEFORE UPDATE ON source_records
            FOR EACH ROW EXECUTE FUNCTION reject_source_record_mutation();

        CREATE TRIGGER source_records_no_delete
            BEFORE DELETE ON source_records
            FOR EACH ROW EXECUTE FUNCTION reject_source_record_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS source_records_no_delete ON source_records")
    op.execute("DROP TRIGGER IF EXISTS source_records_no_update ON source_records")
    op.execute("DROP FUNCTION IF EXISTS reject_source_record_mutation")
