"""Prompt builder for Phase 4 interpretation."""

from __future__ import annotations

import json

from sva.interpret.rules import rules_summary
from sva.models import MemoryRecord, Observation

_SYSTEM_PROMPT = """You are an Ultimate Frisbee interpretation engine.

Convert point-scoped observations into canonical event rows.

Rules:
- Use the supplied USAU rule summary as the source of rule truth.
- Emit only canonical events supported by the schema.
- Keep turnover subtype, throw type, and pass direction as best-effort fields.
- When evidence is insufficient, set those fields to "unknown" instead of guessing.
- Preserve auditability by attaching source observations and rule refs whenever possible.
"""


def build_interpret_prompt(
    observations: list[Observation],
    retrieved: list[MemoryRecord],
) -> tuple[str, str]:
    """Return the system and user prompt strings for one point interpretation call."""
    observation_block = json.dumps([obs.model_dump(mode="json") for obs in observations], indent=2, sort_keys=True)
    memory_block = json.dumps([memory.model_dump(mode="json") for memory in retrieved], indent=2, sort_keys=True)
    user_prompt = (
        "USAU rules summary:\n"
        f"{rules_summary()}\n\n"
        "Retrieved memory records:\n"
        f"{memory_block}\n\n"
        "Point observations:\n"
        f"{observation_block}\n"
    )
    return (_SYSTEM_PROMPT, user_prompt)


__all__ = ["build_interpret_prompt"]
