"""Link dashboard admins to bot users via unique email addresses.

Revision ID: 20260707_0007
Revises: 20260707_0006
Create Date: 2026-07-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260707_0007"
down_revision: str | None = "20260707_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(length=255), nullable=True))
    op.create_unique_constraint("uq_users_email", "users", ["email"])


def downgrade() -> None:
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_column("users", "email")
