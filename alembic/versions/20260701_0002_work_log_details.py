"""Add detailed work log fields.

Revision ID: 20260701_0002
Revises: 20260630_0001
Create Date: 2026-07-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260701_0002"
down_revision: str | None = "20260630_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("work_log_entries", sa.Column("work_date", sa.Date(), nullable=True))
    op.add_column("work_log_entries", sa.Column("start_time", sa.Time(), nullable=True))
    op.add_column("work_log_entries", sa.Column("end_time", sa.Time(), nullable=True))
    op.add_column(
        "work_log_entries",
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Africa/Lagos"),
    )
    op.add_column("work_log_entries", sa.Column("project", sa.String(length=255), nullable=True))
    op.add_column("work_log_entries", sa.Column("site", sa.String(length=255), nullable=True))
    op.add_column(
        "work_log_entries",
        sa.Column("title", sa.String(length=255), nullable=False, server_default="Work update"),
    )
    op.add_column(
        "work_log_entries",
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "work_log_entries",
        sa.Column(
            "confirmation_status", sa.String(length=64), nullable=False, server_default="draft"
        ),
    )
    op.add_column(
        "work_log_entries",
        sa.Column("actions_taken_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "work_log_entries",
        sa.Column("materials_used_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "work_log_entries",
        sa.Column("blockers_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "work_log_entries",
        sa.Column("issues_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "work_log_entries",
        sa.Column("safety_notes_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "work_log_entries",
        sa.Column("confidence", sa.String(length=32), nullable=False, server_default="0"),
    )
    op.execute("UPDATE work_log_entries SET work_date = created_at::date WHERE work_date IS NULL")
    op.alter_column("work_log_entries", "work_date", nullable=False)


def downgrade() -> None:
    op.drop_column("work_log_entries", "confidence")
    op.drop_column("work_log_entries", "safety_notes_json")
    op.drop_column("work_log_entries", "issues_json")
    op.drop_column("work_log_entries", "blockers_json")
    op.drop_column("work_log_entries", "materials_used_json")
    op.drop_column("work_log_entries", "actions_taken_json")
    op.drop_column("work_log_entries", "confirmation_status")
    op.drop_column("work_log_entries", "description")
    op.drop_column("work_log_entries", "title")
    op.drop_column("work_log_entries", "site")
    op.drop_column("work_log_entries", "project")
    op.drop_column("work_log_entries", "timezone")
    op.drop_column("work_log_entries", "end_time")
    op.drop_column("work_log_entries", "start_time")
    op.drop_column("work_log_entries", "work_date")
