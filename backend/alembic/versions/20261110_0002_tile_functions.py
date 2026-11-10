"""Vector tile functions for Martin.

Revision ID: 20261110_0002
Revises: 20261109_0001
"""

from pathlib import Path

from alembic import op

revision = "20261110_0002"
down_revision = "20261109_0001"
branch_labels = None
depends_on = None

TILES_SQL = Path(__file__).resolve().parents[2] / "db" / "tiles.sql"


def upgrade() -> None:
    """Install the functions kept in db/tiles.sql, the single source for Martin."""
    op.execute(TILES_SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute(
        """
        DROP FUNCTION IF EXISTS tiles_edge_accessibility(integer, integer, integer);
        DROP FUNCTION IF EXISTS tiles_barrier(integer, integer, integer);
        """
    )
