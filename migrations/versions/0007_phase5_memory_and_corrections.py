"""phase5 memory and corrections: canonical persistence substrate

Revision ID: 0007_phase5_memory_and_corrections
Revises: 0006_phase4_event_audit_fields
Create Date: 2026-04-24
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007_phase5_memory_and_corrections"
down_revision: str | None = "0006_phase4_event_audit_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memory_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("memory_id", sa.Text(), nullable=False, unique=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column(
            "source",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("embedding_ref", sa.Text(), nullable=True),
        sa.Column("embedding_input", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False, server_default=sa.text("0")),
        sa.Column("corroborations", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_memory_records_kind", "memory_records", ["kind"], unique=False)
    op.create_index("ix_memory_records_scope", "memory_records", ["scope"], unique=False)

    op.create_table(
        "corrections",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("correction_id", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "game_id",
            sa.Text(),
            sa.ForeignKey("jobs.game_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("point_id", sa.Text(), nullable=False),
        sa.Column("point_ordinal", sa.Integer(), nullable=False),
        sa.Column("source_event_id", sa.Text(), nullable=True),
        sa.Column("coach_id", sa.Text(), nullable=False),
        sa.Column("correction_type", sa.Text(), nullable=False),
        sa.Column(
            "original_event",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "proposed_event",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "source_memory_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("note", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_corrections_game_id", "corrections", ["game_id"], unique=False)
    op.create_index("ix_corrections_point_id", "corrections", ["point_id"], unique=False)
    op.create_index("ix_corrections_source_event_id", "corrections", ["source_event_id"], unique=False)
    op.create_index("ix_corrections_coach_id", "corrections", ["coach_id"], unique=False)
    op.create_index("ix_corrections_type", "corrections", ["correction_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_corrections_type", table_name="corrections")
    op.drop_index("ix_corrections_coach_id", table_name="corrections")
    op.drop_index("ix_corrections_source_event_id", table_name="corrections")
    op.drop_index("ix_corrections_point_id", table_name="corrections")
    op.drop_index("ix_corrections_game_id", table_name="corrections")
    op.drop_table("corrections")
    op.drop_index("ix_memory_records_scope", table_name="memory_records")
    op.drop_index("ix_memory_records_kind", table_name="memory_records")
    op.drop_table("memory_records")
