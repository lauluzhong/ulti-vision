"""phase6 jobs: progress and queued submission support

Revision ID: 0009_phase6_job_progress
Revises: 0008_phase5_memory_embeddings
Create Date: 2026-04-25
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_phase6_job_progress"
down_revision: str | None = "0008_phase5_memory_embeddings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("jobs", "video_id", existing_type=sa.Text(), nullable=True)
    op.add_column(
        "jobs",
        sa.Column("stage", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "progress",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "jobs",
        sa.Column("error_message", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("jobs", "error_message")
    op.drop_column("jobs", "progress")
    op.drop_column("jobs", "stage")
    op.alter_column("jobs", "video_id", existing_type=sa.Text(), nullable=False)
