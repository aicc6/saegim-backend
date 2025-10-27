"""Add diary categories table and FK

Revision ID: e739c1fbb8f1
Revises: b4ac8dc12257
Create Date: 2025-10-25 11:00:00.000000+09:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e739c1fbb8f1"
down_revision: Union[str, None] = "b4ac8dc12257"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "diary_categories",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_diary_categories_user_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "name", name="uq_diary_categories_user_id_name"
        ),
    )
    op.create_index(
        op.f("ix_diary_categories_user_id"), "diary_categories", ["user_id"], unique=False
    )

    op.add_column(
        "diaries",
        sa.Column("category_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        op.f("ix_diaries_category_id"), "diaries", ["category_id"], unique=False
    )
    op.create_foreign_key(
        "fk_diaries_category_id",
        "diaries",
        "diary_categories",
        ["category_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_diaries_category_id", "diaries", type_="foreignkey")
    op.drop_index(op.f("ix_diaries_category_id"), table_name="diaries")
    op.drop_column("diaries", "category_id")

    op.drop_index(op.f("ix_diary_categories_user_id"), table_name="diary_categories")
    op.drop_table("diary_categories")
