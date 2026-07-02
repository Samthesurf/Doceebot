"""Add managed document registry.

Revision ID: 20260702_0003
Revises: 20260701_0002
Create Date: 2026-07-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260702_0003"
down_revision: str | None = "20260701_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "managed_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("document_kind", sa.String(length=32), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("storage_backend", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("storage_url", sa.Text(), nullable=True),
        sa.Column("local_path", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("sha256_hex", sa.String(length=64), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False, server_default="uploaded"),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="available"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_managed_documents_org_kind",
        "managed_documents",
        ["org_id", "document_kind"],
    )
    op.create_index(
        "ix_managed_documents_org_updated",
        "managed_documents",
        ["org_id", "updated_at"],
    )
    op.create_table(
        "managed_document_updates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("raw_message_id", sa.Uuid(), nullable=True),
        sa.Column(
            "update_kind",
            sa.String(length=64),
            nullable=False,
            server_default="table_upsert",
        ),
        sa.Column("instruction", sa.Text(), nullable=False, server_default=""),
        sa.Column("changes_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["managed_documents.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["raw_message_id"], ["raw_inbound_messages.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_managed_document_updates_document",
        "managed_document_updates",
        ["document_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_managed_document_updates_document", table_name="managed_document_updates")
    op.drop_table("managed_document_updates")
    op.drop_index("ix_managed_documents_org_updated", table_name="managed_documents")
    op.drop_index("ix_managed_documents_org_kind", table_name="managed_documents")
    op.drop_table("managed_documents")
