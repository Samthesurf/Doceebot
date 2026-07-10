"""Add durable inbound event claims for provider webhook idempotency.

Revision ID: 20260710_0008
Revises: 20260707_0007
Create Date: 2026-07-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260710_0008"
down_revision: str | None = "20260707_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inbound_event_claims",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("platform_message_id", sa.String(length=255), nullable=False),
        sa.Column(
            "claimed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform", "platform_message_id", name="uq_inbound_claim_platform_id"),
    )


def downgrade() -> None:
    op.drop_table("inbound_event_claims")
