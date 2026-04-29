"""Prompt builder for the perception (VLM) stage.

Lives outside the Gemini adapter so any VLM (Gemini, Qwen2-VL, GPT-4V, etc.)
shares the same prompt content. Memory injection is centralized here too —
when corrections accumulate that affect what the VLM should look for
(e.g., 'this team's white jerseys look gray under stadium lights'),
they get appended to the user prompt without touching adapter code.
"""

from __future__ import annotations

import json

from sva.models import MemoryRecord
from sva.perceive.adapters.base import PerceiveWindow

_SYSTEM_PROMPT = """You are an Ultimate Frisbee perception engine.

Your job: extract structured observations from one short window of game footage.
You produce STRUCTURED FACTS, not interpretations. The downstream LLM does the
event reasoning. Your only job is to faithfully describe what is on screen.

Three rules above all:
1. Never fabricate. If you cannot see something clearly, the corresponding field
   stays "unknown" or its safe default. Better to omit than guess.
2. The disc is small, fast, and often invisible. Be honest about disc visibility
   quality. The system relies on you flagging "likely_present_not_visible" rather
   than pretending the disc is in someone's hand when it might not be.
3. Ultimate Frisbee structure: every point starts with a PULL — the defending team
   throws the disc to the offense from their endzone line. Both teams line up on
   their respective endzones until the pull is released. After a goal, players
   walk back, switch direction, and the team that just scored becomes the next
   pull's defense. Use this structure to identify game phase.

For point-boundary detection, the most useful signals you can capture are:
- pre_pull formation: 7 defenders visibly lined up on one endzone, awaiting release
- pull release event: a player on the endzone line throws the disc downfield
- score signals: two straight arms raised overhead (WFDF goal signal), often by
  multiple sideline observers; or a visible scoreboard tick
- between_points: players walking back toward lines, no active disc movement
- live_play: standard contested possession, players actively guarding/cutting
"""

_USER_PROMPT_TEMPLATE = """Analyze this Ultimate Frisbee video window and return exactly one canonical Observation.

Window metadata:
- window_id: {window_id}
- video_id: {video_id}
- video_ts_start_ms: {video_ts_start_ms}
- video_ts_end_ms: {video_ts_end_ms}

Required best-effort fields with explicit guidance:

scene:
- field_visible: full | partial | none — how much of the field is in frame
- camera: sideline | endzone | elevated | handheld | unknown
- lighting: ok | harsh | dim
- multiple_discs_possible: true if any disc-like object on the sideline could
  confuse downstream interpretation

disc:
- visibility_quality: clear | blurry | likely_present_not_visible | absent
- in_air: true if airborne mid-flight (not just held)
- possessor_team: dark | light | none | unknown
- possessor_role: thrower | receiver | defender | none

players:
- dark_count_visible: integer count of dark-jersey players you can see
- light_count_visible: integer count of light-jersey players you can see

formation: ULTIMATE-SPECIFIC, drives point-boundary detection
- phase: choose ONE
  * pre_pull: 7 defenders lined on an endzone line, offense lined on the
    opposite endzone line, awaiting the pull throw
  * pull_in_air: disc has just been pulled, both lines moving
  * live_play: contested possession, normal offense/defense
  * score_celebration: offense in attacking endzone with disc, possible
    arms-up signal nearby
  * between_points: players walking back to lines, no active play
  * stoppage: discussion/call/timeout
  * unknown: cannot tell from this window
- phase_confidence: 0.0 to 1.0
- pull_formation_visible: true ONLY if you see the 7-defenders-on-endzone shape
- arms_raised_count: integer count of distinct people with BOTH arms straight
  overhead (WFDF goal signal). Default 0 if none.
- score_signal: two_hands_up | scoreboard_change | none | unknown
- score_signal_confidence: 0.0 to 1.0

field_orientation:
- scoring_direction: screen_left | screen_right | screen_far | screen_near
  | unclear | unknown — which direction the team in possession is attacking
  relative to the camera frame
- endzone_visible: near | far | both | neither | unknown — whether an endzone
  line/cone is visible in this window
- centerline_x_norm: 0.0 (left edge) to 1.0 (right edge), approximate x of
  the disc's current field-x position. Null if no field lines visible.

actions_detected: free-form list of [tag, confidence] pairs. Useful tags include
pull_release, throw_release, catch, drop, defensive_block, intercept, layout,
sideline_signal_score, sideline_signal_foul. Don't invent tags; omit when unclear.

text_observed: any visible scoreboard text or jersey numbers. Use kind=scoreboard
when reading a digital scoreboard.

confidence_overall: your aggregate confidence that this Observation is faithful.

free_form_note: ONE concise sentence (under 30 words) flagging anything notable
that didn't fit the schema. No speculation.
"""


def build_perceive_prompt(
    window: PerceiveWindow,
    *,
    retrieved: list[MemoryRecord] | None = None,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for one VLM perception call.

    If retrieved memory is supplied (Phase 5+), perceive-relevant guidance
    notes are appended to the user prompt. Memory shapes WHAT the VLM looks
    for, not what it concludes.
    """
    user = _USER_PROMPT_TEMPLATE.format(
        window_id=window.window_id,
        video_id=window.video_id,
        video_ts_start_ms=window.video_ts_start_ms,
        video_ts_end_ms=window.video_ts_end_ms,
    )
    if retrieved:
        memory_block = json.dumps(
            [
                {
                    "memory_id": memory.memory_id,
                    "kind": memory.kind,
                    "tags": memory.tags,
                    "guidance": memory.embedding_input,
                }
                for memory in retrieved
            ],
            indent=2,
            sort_keys=True,
        )
        user = (
            user
            + "\n\nRelevant perception guidance from prior corrections:\n"
            + memory_block
            + "\n\nApply that guidance only where it changes what you would observe."
        )
    return (_SYSTEM_PROMPT, user)


__all__ = ["build_perceive_prompt"]
