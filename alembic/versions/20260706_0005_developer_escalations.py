"""Add developer escalation reports.

Revision ID: 20260706_0005
Revises: 20260706_0004
Create Date: 2026-07-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260706_0005"
down_revision: str | None = "20260706_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "developer_escalations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("raw_message_id", sa.Uuid(), nullable=True),
        sa.Column("org_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("platform", sa.String(length=64), nullable=True),
        sa.Column("report_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("conversation_snapshot_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="pending"),
        sa.Column("destination", sa.String(length=255), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversation_sessions.id"]),
        sa.ForeignKeyConstraint(["raw_message_id"], ["raw_inbound_messages.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_developer_escalations_status_created",
        "developer_escalations",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_developer_escalations_conversation",
        "developer_escalations",
        ["conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_developer_escalations_conversation",
        table_name="developer_escalations",
    )
    op.drop_index(
        "ix_developer_escalations_status_created",
        table_name="developer_escalations",
    )
    op.drop_table("developer_escalations")
