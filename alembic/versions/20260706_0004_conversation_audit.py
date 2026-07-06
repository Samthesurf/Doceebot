"""Add conversation sessions and audit logs.

Revision ID: 20260706_0004
Revises: 20260702_0003
Create Date: 2026-07-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260706_0004"
down_revision: str | None = "20260702_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("platform_chat_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="active"),
        sa.Column("trigger", sa.String(length=64), nullable=False, server_default="first_message"),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_message_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversation_sessions_active_lookup",
        "conversation_sessions",
        ["org_id", "user_id", "platform", "platform_chat_id", "status", "last_message_at"],
    )

    op.add_column("raw_inbound_messages", sa.Column("conversation_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_raw_inbound_messages_conversation_id",
        "raw_inbound_messages",
        "conversation_sessions",
        ["conversation_id"],
        ["id"],
    )

    op.add_column("work_log_entries", sa.Column("conversation_id", sa.Uuid(), nullable=True))
    op.add_column(
        "work_log_entries",
        sa.Column("location_label", sa.String(length=255), nullable=True),
    )
    op.add_column("work_log_entries", sa.Column("location_address", sa.Text(), nullable=True))
    op.add_column("work_log_entries", sa.Column("category", sa.String(length=128), nullable=True))
    op.add_column(
        "work_log_entries",
        sa.Column("participants_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "work_log_entries",
        sa.Column("equipment_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "work_log_entries",
        sa.Column("measurements_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "work_log_entries",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_work_log_entries_conversation_id",
        "work_log_entries",
        "conversation_sessions",
        ["conversation_id"],
        ["id"],
    )

    op.create_table(
        "conversation_turns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("raw_message_id", sa.Uuid(), nullable=True),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=True),
        sa.Column("platform_message_id", sa.String(length=255), nullable=True),
        sa.Column("message_type", sa.String(length=64), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("media_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("raw_payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversation_sessions.id"]),
        sa.ForeignKeyConstraint(["raw_message_id"], ["raw_inbound_messages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversation_turns_session_time",
        "conversation_turns",
        ["conversation_id", "occurred_at"],
    )

    op.create_table(
        "llm_audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("raw_message_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("output_json", sa.Text(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversation_sessions.id"]),
        sa.ForeignKeyConstraint(["raw_message_id"], ["raw_inbound_messages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_llm_audit_logs_conversation_created",
        "llm_audit_logs",
        ["conversation_id", "created_at"],
    )
    op.create_index("ix_llm_audit_logs_raw_message", "llm_audit_logs", ["raw_message_id"])


def downgrade() -> None:
    op.drop_index("ix_llm_audit_logs_raw_message", table_name="llm_audit_logs")
    op.drop_index("ix_llm_audit_logs_conversation_created", table_name="llm_audit_logs")
    op.drop_table("llm_audit_logs")
    op.drop_index("ix_conversation_turns_session_time", table_name="conversation_turns")
    op.drop_table("conversation_turns")
    op.drop_constraint(
        "fk_work_log_entries_conversation_id",
        "work_log_entries",
        type_="foreignkey",
    )
    op.drop_column("work_log_entries", "updated_at")
    op.drop_column("work_log_entries", "measurements_json")
    op.drop_column("work_log_entries", "equipment_json")
    op.drop_column("work_log_entries", "participants_json")
    op.drop_column("work_log_entries", "category")
    op.drop_column("work_log_entries", "location_address")
    op.drop_column("work_log_entries", "location_label")
    op.drop_column("work_log_entries", "conversation_id")
    op.drop_constraint(
        "fk_raw_inbound_messages_conversation_id",
        "raw_inbound_messages",
        type_="foreignkey",
    )
    op.drop_column("raw_inbound_messages", "conversation_id")
    op.drop_index("ix_conversation_sessions_active_lookup", table_name="conversation_sessions")
    op.drop_table("conversation_sessions")
