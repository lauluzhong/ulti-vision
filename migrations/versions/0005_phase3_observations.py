"""phase3 observations: persisted perception output cache

Revision ID: 0005_phase3_observations
Revises: 0004_phase2_point_scoped_events
Create Date: 2026-04-23
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_phase3_observations"
down_revision: str | None = "0004_phase2_point_scoped_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "observations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("observation_id", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "game_id",
            sa.Text(),
            sa.ForeignKey("jobs.game_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("point_id", sa.Text(), nullable=False),
        sa.Column("point_ordinal", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Text(), nullable=False),
        sa.Column("window_id", sa.Text(), nullable=False),
        sa.Column("prompt_version_hash", sa.Text(), nullable=False),
        sa.Column("video_ts_start_ms", sa.BigInteger(), nullable=False),
        sa.Column("video_ts_end_ms", sa.BigInteger(), nullable=False),
        sa.Column("observation_ts_ms", sa.BigInteger(), nullable=False),
        sa.Column("confidence_overall", sa.Numeric(4, 3), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False, server_default=sa.text("'1.0'")),
        sa.Column("raw_response_ref", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_observations_game_id", "observations", ["game_id"], unique=False)
    op.create_index("ix_observations_point_id", "observations", ["point_id"], unique=False)
    op.create_index("ix_observations_video_id", "observations", ["video_id"], unique=False)
    op.create_index("ix_observations_window_id", "observations", ["window_id"], unique=False)
    op.create_index(
        "ix_observations_cache_key",
        "observations",
        ["video_id", "window_id", "prompt_version_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_observations_cache_key", table_name="observations")
    op.drop_index("ix_observations_window_id", table_name="observations")
    op.drop_index("ix_observations_video_id", table_name="observations")
    op.drop_index("ix_observations_point_id", table_name="observations")
    op.drop_index("ix_observations_game_id", table_name="observations")
    op.drop_table("observations")
