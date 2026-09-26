"""per-level reward columns (levels 2-4 locked to zero)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-26 03:30:00

The reward table is now built from a per-level column, so the amount for every
level flows through one formula. Levels 2-4 carry a CHECK (= 0): the structure
exists and is wired through, but the database refuses to store any payout for
them. Paying levels beyond the first is a money-circulation scheme and stays
impossible by construction (see SECURITY.md / docs/ADMIN.md).
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

LEVELS = (2, 3, 4)


def upgrade() -> None:
    for level in LEVELS:
        column = f"level_{level}_reward_paise"
        op.add_column("campaigns", sa.Column(column, sa.BigInteger(), nullable=False, server_default="0"))
        op.create_check_constraint(f"level_{level}_reward_zero", "campaigns", f"{column} = 0")


def downgrade() -> None:
    for level in LEVELS:
        # Short name: the metadata naming convention (base.NAMING) adds the
        # "ck_campaigns_" prefix, exactly as create_check_constraint did above.
        op.drop_constraint(f"level_{level}_reward_zero", "campaigns", type_="check")
        op.drop_column("campaigns", f"level_{level}_reward_paise")
