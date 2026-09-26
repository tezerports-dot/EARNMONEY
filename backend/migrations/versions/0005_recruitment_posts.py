"""recruitment_posts table

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-26 05:40:00

Job openings the admin posts; the app's Recruitment tab lists the open ones.
Plain content, no personal or financial data.
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recruitment_posts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("location", sa.String(length=120), nullable=True),
        sa.Column("employment_type", sa.String(length=60), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("apply_url", sa.Text(), nullable=True),
        sa.Column("apply_email", sa.String(length=200), nullable=True),
        sa.Column("is_open", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("apply_email IS NULL OR apply_email <> ''", name=op.f("ck_recruitment_posts_apply_email_not_blank")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recruitment_posts")),
    )
    op.create_index("ix_recruitment_posts_open", "recruitment_posts", ["is_open", "sort_order", "id"])


def downgrade() -> None:
    op.drop_index("ix_recruitment_posts_open", table_name="recruitment_posts")
    op.drop_table("recruitment_posts")
