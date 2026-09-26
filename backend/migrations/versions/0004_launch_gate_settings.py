"""launch-gate settings on app_settings

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-26 05:20:00

The Telegram Mini App launch gate: when enabled, the app sends each user back
through a Mini App (which shows an Adsgram ad) from their own verified Telegram
account before it shows their data. These are the public, non-secret settings
that drive it. Off by default — the operator turns it on in the admin panel.
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column("launch_gate_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "app_settings",
        sa.Column("launch_gate_pass_seconds", sa.Integer(), nullable=False, server_default="21600"),
    )
    op.add_column("app_settings", sa.Column("miniapp_short_name", sa.String(length=64), nullable=True))
    op.add_column("app_settings", sa.Column("adsgram_block_id", sa.String(length=64), nullable=True))
    op.create_check_constraint("launch_gate_pass_seconds", "app_settings", "launch_gate_pass_seconds BETWEEN 60 AND 604800")


def downgrade() -> None:
    op.drop_constraint("launch_gate_pass_seconds", "app_settings", type_="check")
    op.drop_column("app_settings", "adsgram_block_id")
    op.drop_column("app_settings", "miniapp_short_name")
    op.drop_column("app_settings", "launch_gate_pass_seconds")
    op.drop_column("app_settings", "launch_gate_enabled")
