"""index unverified signups by referrer

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-24 23:40:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

PENDING = sa.text("status = 'PENDING_VERIFICATION'")


def upgrade() -> None:
    # The dashboard counts a referrer's friends who haven't verified yet.
    # Without this index Postgres walks every pending signup on the system
    # (measured with bench/run.py; see docs/PERFORMANCE.md).
    op.create_index(
        "ix_users_referrer_pending", "users", ["referrer_id", "pending_expires_at"], unique=False, postgresql_where=PENDING
    )


def downgrade() -> None:
    op.drop_index("ix_users_referrer_pending", table_name="users", postgresql_where=PENDING)
