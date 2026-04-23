"""phase2 ingest sources: jobs source audit fields + rights_acks table

Revision ID: 0002_phase2_sources_and_rights_acks
Revises: 0001_phase1_foundation
Create Date: 2026-04-23
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_phase2_sources_and_rights_acks"
down_revision: str | None = "0001_phase1_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("source_kind", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("source_url", sa.Text(), nullable=True))
    op.create_index("ix_jobs_source_kind", "jobs", ["source_kind"], unique=False)

    op.create_table(
        "rights_acks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("game_id", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_host", sa.Text(), nullable=False),
        sa.Column("caller_id", sa.Text(), nullable=False),
        sa.Column(
            "acknowledged_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_rights_acks_game_id", "rights_acks", ["game_id"], unique=False)
    op.create_index("ix_rights_acks_source_host", "rights_acks", ["source_host"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_rights_acks_source_host", table_name="rights_acks")
    op.drop_index("ix_rights_acks_game_id", table_name="rights_acks")
    op.drop_table("rights_acks")
    op.drop_index("ix_jobs_source_kind", table_name="jobs")
    op.drop_column("jobs", "source_url")
    op.drop_column("jobs", "source_kind")
