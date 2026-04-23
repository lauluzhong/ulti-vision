"""phase2 point-scoped events: require point metadata on persisted events

Revision ID: 0004_phase2_point_scoped_events
Revises: 0003_phase2_points
Create Date: 2026-04-23
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0004_phase2_point_scoped_events"
down_revision: str | None = "0003_phase2_points"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("events", sa.Column("point_ordinal", sa.Integer(), nullable=True))
    op.add_column("events", sa.Column("in_point_ts_ms", sa.BigInteger(), nullable=True))

    op.execute(
        """
        UPDATE events
        SET
            point_id = COALESCE(point_id, game_id || ':pt_001'),
            point_ordinal = COALESCE(point_ordinal, 1),
            in_point_ts_ms = COALESCE(in_point_ts_ms, video_ts_ms)
        """
    )

    op.alter_column("events", "point_id", existing_type=sa.Text(), nullable=False)
    op.alter_column("events", "point_ordinal", existing_type=sa.Integer(), nullable=False)
    op.alter_column("events", "in_point_ts_ms", existing_type=sa.BigInteger(), nullable=False)
    op.create_index("ix_events_game_id_point_id", "events", ["game_id", "point_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_events_game_id_point_id", table_name="events")
    op.alter_column("events", "point_id", existing_type=sa.Text(), nullable=True)
    op.drop_column("events", "in_point_ts_ms")
    op.drop_column("events", "point_ordinal")
