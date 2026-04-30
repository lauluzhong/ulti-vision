"""Prompt builder for the interpretation (LLM) stage.

v0 scope: produce honest counts of POINTS, TURNOVERS, and PASSES (completions).
Goals are inferred from score signals where present. Throw type, pass direction,
and turnover subtype degrade to "unknown" when evidence is thin — better
honest-unknown counts than fabricated detail.
"""

from __future__ import annotations

import json

from sva.interpret.rules import rules_summary
from sva.models import MemoryRecord, Observation

_SYSTEM_PROMPT = """You are an Ultimate Frisbee interpretation engine.

You convert one point's observations into canonical event rows. The
observations were produced by a VLM watching ~1-3 frames per second of
gameplay; treat them as ground truth for what was visible.

v0 SCOPE — what you must produce:
- Whether a goal was scored in this point (one Event with type="goal")
- Each completed pass / catch the VLM saw (Event with type="completion")
- Each turnover the VLM saw (Event with type="turnover")
- Possession transitions when clearly visible (type="possession_start" / "possession_end")

For each event you emit:
- type: required, drawn from the canonical event taxonomy
- team: dark | light | none | unknown — only set non-unknown when the
  observation evidence makes the team clear
- video_ts_ms: an integer timestamp anchored to the source observation; use
  the observation's observation_ts_ms if no better timestamp is implied
- source_observations: list of observation_ids that justified this event

Best-effort fields — DEGRADE TO UNKNOWN when evidence is thin:
- turnover_subtype (throwaway/drop/block/out_of_bounds/unknown): only set
  when an action_tag like "drop" or "defensive_block" or "out_of_bounds"
  is present with confidence
- throw_type (forehand/backhand/hammer/blade/unknown): only set when the
  action_tag specifies it; otherwise unknown
- pass_direction (up-field/down-field/lateral/unknown): only set when the
  observation's field_orientation.scoring_direction is known AND the
  disc's centerline_x_norm trajectory supports the call. Otherwise unknown.

WFDF rules to honor:
- A goal requires the catch to land in the attacking endzone (WFDF-13.1).
- A turnover transfers possession (WFDF-13.2).
- Possession cannot flip teams without an intervening turnover or goal
  (WFDF-13.2/12.1).

Return ONLY a JSON array of Event objects. No prose, no preamble.

When you don't see any events for a point (e.g., the VLM observations are
mostly "between_points" or "unknown"), return an empty array.

Quality > recall: missing an event the VLM didn't clearly see is better
than fabricating one. The system has a coach-correction loop that will
add the missed events back; it cannot easily remove fabricated ones.
"""


def build_interpret_prompt(
    observations: list[Observation],
    retrieved: list[MemoryRecord],
) -> tuple[str, str]:
    """Return the system and user prompt strings for one point interpretation call."""
    observation_block = json.dumps([obs.model_dump(mode="json") for obs in observations], indent=2, sort_keys=True)
    memory_block = json.dumps([memory.model_dump(mode="json") for memory in retrieved], indent=2, sort_keys=True)
    user_prompt = (
        "WFDF rules summary:\n"
        f"{rules_summary()}\n\n"
        "Retrieved memory records (prior coach corrections — apply where they\n"
        "change how you should interpret these specific observations):\n"
        f"{memory_block}\n\n"
        "Point observations (chronological — typically 2-15 windows):\n"
        f"{observation_block}\n"
    )
    return (_SYSTEM_PROMPT, user_prompt)


__all__ = ["build_interpret_prompt"]
