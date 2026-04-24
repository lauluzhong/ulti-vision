"""phase5 memory embeddings: repeatable semantic ranking substrate

Revision ID: 0008_phase5_memory_embeddings
Revises: 0007_phase5_memory_and_corrections
Create Date: 2026-04-24
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_phase5_memory_embeddings"
down_revision: str | None = "0007_phase5_memory_and_corrections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memory_embeddings",
        sa.Column(
            "memory_id",
            sa.Text(),
            sa.ForeignKey("memory_records.memory_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column(
            "vector",
            postgresql.ARRAY(sa.Float(asdecimal=False)),
            nullable=False,
        ),
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
    op.create_index(
        "ix_memory_embeddings_provider_model_id",
        "memory_embeddings",
        ["provider", "model_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_memory_embeddings_provider_model_id", table_name="memory_embeddings")
    op.drop_table("memory_embeddings")
