"""Per-edge slope from the elevation stage and field-measured overrides.

Revision ID: 20261110_0003
Revises: 20261110_0002
"""

from alembic import op

revision = "20261110_0003"
down_revision = "20261110_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE edge
            ADD COLUMN slope_pct real,
            ADD COLUMN max_slope_pct real,
            ADD COLUMN slope_source text
                CHECK (slope_source IS NULL OR slope_source IN ('dem', 'dem_lowres', 'osm_incline')),
            ADD COLUMN overrides jsonb NOT NULL DEFAULT '{}'::jsonb;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE edge
            DROP COLUMN IF EXISTS overrides,
            DROP COLUMN IF EXISTS slope_source,
            DROP COLUMN IF EXISTS max_slope_pct,
            DROP COLUMN IF EXISTS slope_pct;
        """
    )
