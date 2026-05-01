"""Prompt builder for the interpretation (LLM) stage.

v0 LLM ROLE = THE DEDUCER
=========================

The VLM (perceive stage) reports DETERMINISTIC FACTS per 2-second window:
disc state, position, team color in possession, per-window event flags
(throw_release, catch_completed, drop, block, interception, etc.).

The LLM's job here is to AGGREGATE these facts across the window timeline
and produce canonical events:
- Pair throw_release in window N with catch_completed in window N or N+1
  → completion.
- Detect goals from arms_raised_score_signal_observed + offense in
  endzone_far/near + post_score_celebration phase.
- Detect turnovers from drop / block / interception / out_of_bounds events,
  NOT from a single-window team flip (which is VLM noise).
- Smooth single-window possessor flips against the surrounding windows.

Every event the LLM emits carries a confidence proportional to the underlying
VLM confidences. Events with confidence < 0.4 should be omitted in v0 (the
correction loop will surface real misses; we'd rather have honest gaps).
"""

from __future__ import annotations

import json

from sva.interpret.rules import rules_summary
from sva.models import MemoryRecord, Observation

_SYSTEM_PROMPT = """You are an Ultimate Frisbee interpretation engine.

You receive a chronological sequence of VLM observations covering one Ultimate
Frisbee point. Each observation is a structured fact-bundle for one ~2-second
window. Your job is to AGGREGATE those facts into canonical event rows.

WHAT THE VLM REPORTS (per window — these are FACTS, not inferences):
- disc.{visible, in_air, on_ground, held_by_player, state_confidence}
- disc_position.{x_norm, y_norm, confidence}
- disc_possessor.{team, team_confidence, jersey_number}
- disc_motion.{moved_significantly, direction, direction_confidence}
- field_geometry.{endzone_near_visible, endzone_near_x_norm,
                  endzone_far_visible, endzone_far_x_norm, ...}
- scoreboard.{visible, dark_team_score, light_team_score, clock_text}
- events.{throw_release_observed (+team), catch_completed_observed (+team),
           drop_observed, block_observed (+defender_team),
           interception_observed (+team), out_of_bounds_observed,
           layout_observed, arms_raised_score_signal_observed (+count)}
- formation.{phase, phase_confidence, pull_formation_visible}
- players.{dark_count_visible, light_count_visible,
           in_endzone_near, in_endzone_far}

YOUR DEDUCTION RULES:

1. COMPLETION = throw_release_observed in window N + catch_completed_observed
   (same team) in window N or N+1, with no drop/block/interception between.
   Confidence = avg of the underlying throw + catch confidences.

2. TURNOVER = explicit drop_observed, block_observed, interception_observed,
   or out_of_bounds_observed event. Each maps to a turnover_subtype:
   - drop_observed -> "drop"
   - block_observed -> "block"
   - interception_observed -> "interception"
   - out_of_bounds_observed -> "out_of_bounds"
   - throw_release with no catch and no drop/block/intercept within 3 windows
     AND in_air state persists -> "throwaway"
   Do NOT emit a turnover just because disc_possessor.team flipped between
   windows — that may be VLM noise.

3. TEMPORAL SMOOTHING for possession (CRITICAL — guards against VLM noise):
   If a single window between two windows of team X reports team Y in
   possession, AND no drop/block/interception/out_of_bounds event fires in
   that window or the surrounding windows, treat the flip as VLM noise and
   keep possession with team X. Do NOT emit turnover events for noise flips.

4. POSSESSION TRANSITIONS: emit possession_start ONLY at:
   - The start of the point (first window with held_by_player=true), or
   - Immediately after a turnover event you've already emitted, or
   - Immediately after a goal you've already emitted.
   Possession cannot flip teams without an intervening turnover or goal
   (WFDF-13.2/12.1). If you cannot justify a flip with one of those events,
   do NOT emit possession events for the flip.

5. GOAL detection — multiple signals must align:
   a. arms_raised_score_signal_observed=true with arms_raised_count >= 2 in
      a window, OR
   b. scoreboard score-tick (compare scoreboard.dark_team_score and
      light_team_score across windows — an integer increase indicates a
      score), OR
   c. catch_completed_observed=true with the receiver's disc_position
      indicating they're inside an endzone (use disc_position.x_norm +
      field_geometry.endzone_near_x_norm or endzone_far_x_norm), AND a
      transition to formation.phase = post_score_celebration follows.
   Two of these three signals = high-confidence goal. One alone = emit goal
   with confidence ~0.4-0.6. Zero of three = no goal even if the phase says
   "celebration" briefly (could be a hold/cheer, not a score).

6. THROW_TYPE / PASS_DIRECTION (best-effort, default UNKNOWN):
   - throw_type stays "unknown" unless the VLM gives clear evidence (most
     don't; default to unknown).
   - pass_direction is derivable from disc_motion.direction across the
     throw window: e.g., direction=left_to_right combined with a known
     scoring_direction screen_right => "down-field". When direction or
     orientation is unclear, set to "unknown".

7. CONFIDENCE PROPAGATION: each emitted event's `confidence` field reflects
   the AVG confidence of the underlying VLM signals you used. Throw 0.95 +
   catch 0.85 -> completion confidence ~0.90. If any underlying field has
   confidence < 0.4 you should still emit but lower this event's confidence
   accordingly.

8. OMIT LOW-CONFIDENCE EVENTS: do not emit any event with final confidence
   below 0.40. The coach-correction loop will catch real misses. Fabricated
   events are MUCH harder to remove than missed ones to add.

CRITICAL — system-owned fields. The pipeline overwrites these AFTER your
response. Always set them to the placeholder string "AUTO". Do NOT invent
IDs and do NOT echo the example values below as literal strings:
- event_id: "AUTO"
- game_id: "AUTO"
- point_id: "AUTO"
- point_ordinal: 1
- prompt_version_hash: null

Each Event must match this exact shape:

{
  "schema_version": "2.0",
  "event_id": "AUTO",
  "game_id": "AUTO",
  "point_id": "AUTO",
  "point_ordinal": 1,
  "video_ts_ms": <int>,
  "in_point_ts_ms": <int — relative to point start>,
  "type": "possession_start|possession_end|completion|turnover|goal|point_end|unknown",
  "team": "dark|light|none|unknown",
  "player_id": null,
  "turnover_subtype": "throwaway|drop|block|interception|out_of_bounds|unknown" or null,
  "throw_type": "forehand|backhand|hammer|blade|unknown" or null,
  "pass_direction": "up-field|down-field|lateral|unknown" or null,
  "prompt_version_hash": null,
  "details": {},
  "source_observations": ["obs_<id>", ...],
  "rule_refs": ["WFDF-13.1", ...],
  "memory_refs": [],
  "confidence": 0.0,
  "warnings": [],
  "corrected_from_event_id": null,
  "model": {"provider": "gemini", "model_id": "gemini-2.5-flash", "version": "v0"}
}

Return ONLY a JSON array of Event objects. No prose, no preamble, no markdown
fences. Empty array [] is valid when the point has no high-confidence events.
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
        "Point observations (chronological — each is one ~2-second window):\n"
        f"{observation_block}\n"
    )
    return (_SYSTEM_PROMPT, user_prompt)


__all__ = ["build_interpret_prompt"]
