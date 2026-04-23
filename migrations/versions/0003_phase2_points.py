"""phase2 points: first-class persisted point boundaries

Revision ID: 0003_phase2_points
Revises: 0002_phase2_sources_and_rights_acks
Create Date: 2026-04-23
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_phase2_points"
down_revision: str | None = "0002_phase2_sources_and_rights_acks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "points",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "point_id",
            sa.Text(),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "game_id",
            sa.Text(),
            sa.ForeignKey("jobs.game_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("point_ordinal", sa.Integer(), nullable=False),
        sa.Column("start_video_ts_ms", sa.BigInteger(), nullable=False),
        sa.Column("end_video_ts_ms", sa.BigInteger(), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column(
            "boundary_evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_points_game_id", "points", ["game_id"], unique=False)
    op.create_index("ix_points_game_id_point_ordinal", "points", ["game_id", "point_ordinal"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_points_game_id_point_ordinal", table_name="points")
    op.drop_index("ix_points_game_id", table_name="points")
    op.drop_table("points")
