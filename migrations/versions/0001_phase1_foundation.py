"""phase1 foundation: jobs + events tables, pgvector extension

Revision ID: 0001_phase1_foundation
Revises:
Create Date: 2026-04-21
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_phase1_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pgvector is installed in Phase 5; extension guard is idempotent.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("game_id", sa.Text(), nullable=False, index=True, unique=True),
        sa.Column("video_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column(
            "cost_usd",
            sa.Numeric(12, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("duration_s", sa.Numeric(10, 3), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # pgcrypto provides gen_random_uuid().
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_id", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "game_id",
            sa.Text(),
            sa.ForeignKey("jobs.game_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("point_id", sa.Text(), nullable=True, index=True),
        sa.Column("video_ts_ms", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False, index=True),
        sa.Column("team", sa.Text(), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "schema_version",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'1.0'"),
        ),
        sa.Column(
            "source_observations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "memory_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("jobs")
    # Intentionally leave pgvector + pgcrypto extensions in place on downgrade.
