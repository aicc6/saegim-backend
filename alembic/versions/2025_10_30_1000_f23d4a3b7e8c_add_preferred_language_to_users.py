"""Add preferred language column to users

Revision ID: f23d4a3b7e8c
Revises: e739c1fbb8f1
Create Date: 2025-10-30 10:00:00.000000+09:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f23d4a3b7e8c"
down_revision: Union[str, None] = "e739c1fbb8f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("preferred_language", sa.String(length=10), nullable=True),
    )
    op.create_check_constraint(
        "ck_users_preferred_language",
        "users",
        "preferred_language IS NULL OR preferred_language IN ('ko','en','ja')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_preferred_language", "users", type_="check")
    op.drop_column("users", "preferred_language")
