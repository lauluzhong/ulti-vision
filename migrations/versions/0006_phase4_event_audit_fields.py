"""phase4 events: widen persisted audit fields for canonical timelines

Revision ID: 0006_phase4_event_audit_fields
Revises: 0005_phase3_observations
Create Date: 2026-04-24
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006_phase4_event_audit_fields"
down_revision: str | None = "0005_phase3_observations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("events", sa.Column("turnover_subtype", sa.Text(), nullable=True))
    op.add_column("events", sa.Column("throw_type", sa.Text(), nullable=True))
    op.add_column("events", sa.Column("pass_direction", sa.Text(), nullable=True))
    op.add_column("events", sa.Column("prompt_version_hash", sa.Text(), nullable=True))
    op.add_column(
        "events",
        sa.Column(
            "rule_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "events",
        sa.Column(
            "warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("events", "warnings")
    op.drop_column("events", "rule_refs")
    op.drop_column("events", "prompt_version_hash")
    op.drop_column("events", "pass_direction")
    op.drop_column("events", "throw_type")
    op.drop_column("events", "turnover_subtype")
