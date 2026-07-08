"""Add full-text search support with pg_trgm and tsvector columns.

Revision ID: 20260707_0006
Revises: 20260706_0005
Create Date: 2026-07-07
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260707_0006"
down_revision: str | None = "20260706_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Install pg_trgm extension (safe — IF NOT EXISTS)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # ── work_log_entries ──────────────────────────────────────────────
    # Generated tsvector column indexing all text + JSON array fields
    op.execute(
        """
        ALTER TABLE work_log_entries
        ADD COLUMN IF NOT EXISTS search_vector tsvector
        GENERATED ALWAYS AS (
            to_tsvector('english',
                coalesce(title, '') || ' ' ||
                coalesce(description, '') || ' ' ||
                coalesce(summary, '') || ' ' ||
                coalesce(project, '') || ' ' ||
                coalesce(site, '') || ' ' ||
                coalesce(location_label, '') || ' ' ||
                coalesce(category, '') || ' ' ||
                coalesce(participants_json, '') || ' ' ||
                coalesce(materials_used_json, '') || ' ' ||
                coalesce(equipment_json, '') || ' ' ||
                coalesce(actions_taken_json, '')
            )
        ) STORED
        """
    )

    # GIN index on the tsvector column
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_work_log_entries_search_vector "
        "ON work_log_entries USING gin (search_vector)"
    )

    # Trigram GIN indexes on individual text columns for fuzzy matching
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_work_log_entries_title_trgm "
        "ON work_log_entries USING gin (title gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_work_log_entries_description_trgm "
        "ON work_log_entries USING gin (description gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_work_log_entries_summary_trgm "
        "ON work_log_entries USING gin (summary gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_work_log_entries_project_trgm "
        "ON work_log_entries USING gin (project gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_work_log_entries_site_trgm "
        "ON work_log_entries USING gin (site gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_work_log_entries_location_label_trgm "
        "ON work_log_entries USING gin (location_label gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_work_log_entries_category_trgm "
        "ON work_log_entries USING gin (category gin_trgm_ops)"
    )

    # ── conversation_turns ────────────────────────────────────────────
    # Generated tsvector column indexing body_text only
    op.execute(
        """
        ALTER TABLE conversation_turns
        ADD COLUMN IF NOT EXISTS search_vector tsvector
        GENERATED ALWAYS AS (
            to_tsvector('english', coalesce(body_text, ''))
        ) STORED
        """
    )

    # GIN index on the tsvector column
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_conversation_turns_search_vector "
        "ON conversation_turns USING gin (search_vector)"
    )

    # Trigram GIN index on body_text for fuzzy matching
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_conversation_turns_body_text_trgm "
        "ON conversation_turns USING gin (body_text gin_trgm_ops)"
    )

    # ── conversation_sessions ─────────────────────────────────────────
    # Trigram GIN index on title for fuzzy matching session titles
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_conversation_sessions_title_trgm "
        "ON conversation_sessions USING gin (title gin_trgm_ops)"
    )


def downgrade() -> None:
    # ── Remove trigram indexes ──
    op.execute("DROP INDEX IF EXISTS ix_conversation_sessions_title_trgm")
    op.execute("DROP INDEX IF EXISTS ix_conversation_turns_body_text_trgm")

    op.execute("DROP INDEX IF EXISTS ix_work_log_entries_category_trgm")
    op.execute("DROP INDEX IF EXISTS ix_work_log_entries_location_label_trgm")
    op.execute("DROP INDEX IF EXISTS ix_work_log_entries_site_trgm")
    op.execute("DROP INDEX IF EXISTS ix_work_log_entries_project_trgm")
    op.execute("DROP INDEX IF EXISTS ix_work_log_entries_summary_trgm")
    op.execute("DROP INDEX IF EXISTS ix_work_log_entries_description_trgm")
    op.execute("DROP INDEX IF EXISTS ix_work_log_entries_title_trgm")

    # ── Remove GIN indexes on tsvector columns ──
    op.execute("DROP INDEX IF EXISTS ix_conversation_turns_search_vector")
    op.execute("DROP INDEX IF EXISTS ix_work_log_entries_search_vector")

    # ── Drop generated tsvector columns ──
    op.execute("ALTER TABLE conversation_turns DROP COLUMN IF EXISTS search_vector")
    op.execute("ALTER TABLE work_log_entries DROP COLUMN IF EXISTS search_vector")

    # NOTE: pg_trgm extension is intentionally NOT removed in downgrade
    # because other tables/indexes may depend on it.
