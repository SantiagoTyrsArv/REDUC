"""Token version per user, so sessions can be revoked.

Revision ID: 20261110_0004
Revises: 20261110_0003
"""

from alembic import op

revision = "20261110_0004"
down_revision = "20261110_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE app_user ADD COLUMN token_version integer NOT NULL DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE app_user DROP COLUMN IF EXISTS token_version")
