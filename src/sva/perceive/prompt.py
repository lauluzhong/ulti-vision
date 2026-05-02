"""Prompt builder for the perception (VLM) stage.

Lives outside the Gemini adapter so any VLM (Gemini, Qwen2-VL, GPT-4V, etc.)
shares the same prompt content. Memory injection is centralized here too —
when corrections accumulate that affect what the VLM should look for
(e.g., 'this team's white jerseys look gray under stadium lights'),
they get appended to the user prompt without touching adapter code.

DETERMINISTIC FACT-OUTPUT DESIGN (v2.0)
=======================================

The VLM's job here is to be a deterministic OBSERVER, not a reasoner. It
reports facts about a single 2-second window with frame-level evidence.
Every interpretive question (Was that a completion? Was that a turnover?
Did the team score?) is the LLM's job, downstream.

Concretely:
- We do NOT ask "is this a thrower or a receiver?" (interpretation).
- We DO ask "is the disc held? is it in_air? did the disc transition from
  held to in_air this window?" (facts).
- Every field has a confidence so low-confidence observations don't infect
  high-confidence ones during LLM aggregation.
- Free-form narration is demoted to `debug_note` — the LLM ignores it; we
  keep it ONLY for human-in-the-loop diagnosis.
"""

from __future__ import annotations

import json

from sva.models import MemoryRecord
from sva.perceive.adapters.base import PerceiveWindow

_SYSTEM_PROMPT = """You are an Ultimate Frisbee perception engine.

Your role is DETERMINISTIC OBSERVER. You watch one short 2-second video window
and report structured FACTS about what is visible. You do NOT decide whether
events succeeded, you do NOT infer player roles, you do NOT track game-level
state across windows. The downstream LLM does all reasoning.

Three rules above all:

1. NEVER fabricate. If you cannot see something clearly, the corresponding field
   stays at its default ("unknown" / null / false / 0) and the matching
   *_confidence stays at 0. Better to leave a field empty than to guess.

2. Every interpretive question — "is this player about to throw?" "is this
   completed?" "who is on offense?" — is OUT OF SCOPE for you. You report
   observable physical state only:
       - Is the disc visible? Where in the frame?
       - Is the disc in the air, on the ground, or held by a player?
       - Which team color is in contact with the disc, if any?
       - Did the disc visibly change state within this window's frames
         (held -> air, air -> held, air -> ground)?

3. Confidence is mandatory. Each non-trivial field has a *_confidence in
   [0.0, 1.0]. Use confidence honestly: 0.95 only when you are nearly
   certain; 0.5 when ambiguous; 0.1 when you're guessing. The LLM weights
   downstream events by these confidences.

About Ultimate Frisbee structure (background — to help you classify game phase
correctly, NOT to interpret gameplay):

- Each point starts with a PULL — defense throws the disc to the offense from
  defense's endzone line. Both teams line up on their endzones.
- After the pull, LIVE_PLAY: contested possession, throws, catches.
- A goal is scored when the offense catches a pass in the attacking endzone.
- Between points, players walk back to lines (BETWEEN_POINTS).

Game phase categories you'll classify:
- pre_pull: 7 defenders visibly on an endzone line, awaiting release
- pull_in_air: disc is mid-flight from a pull throw
- live_play: standard contested play
- post_score_celebration: offense in attacking endzone, possible arms-up signal
- between_points: players walking back, no active play
- stoppage: discussion/call/timeout
- unknown: cannot tell from this window
"""


# JSON shape — kept minimal but exact. Default values shown are the SAFE
# defaults the VLM should fall back to when uncertain. Comments inside the
# JSON block are for the model's reading; the actual output must be valid JSON.
_USER_PROMPT_TEMPLATE = """Observe this 2-second video window and return ONE JSON object matching the
exact shape below. Do NOT add prose, markdown fences, or fields outside the schema.

CRITICAL — system-owned fields. Set these to the placeholder string "AUTO".
The pipeline overwrites them after your response:
- observation_id: "AUTO"
- window_id: "AUTO"
- video_id: "AUTO"
- raw_response_ref: null

Window metadata (use these timestamps verbatim):
- window_id: {window_id}
- video_id: {video_id}
- video_ts_start_ms: {video_ts_start_ms}
- video_ts_end_ms: {video_ts_end_ms}

Return EXACTLY this JSON shape:

{{
  "schema_version": "2.0",
  "observation_id": "AUTO",
  "window_id": "AUTO",
  "video_id": "AUTO",
  "video_ts_start_ms": {video_ts_start_ms},
  "video_ts_end_ms": {video_ts_end_ms},
  "observation_ts_ms": <int, midpoint of window>,

  "scene": {{
    "field_visible": "full|partial|none",
    "camera": "sideline|endzone|elevated|handheld|unknown",
    "lighting": "ok|harsh|dim",
    "obstruction": false,
    "multiple_discs_possible": false
  }},

  "disc": {{
    "visible": true,
    "visibility_quality": "clear|blurry|likely_present_not_visible|absent",
    "in_air": false,
    "on_ground": false,
    "held_by_player": false,
    "state_confidence": 0.0
  }},

  "disc_position": {{
    "x_norm": null,
    "y_norm": null,
    "confidence": 0.0
  }},

  "disc_possessor": {{
    "team": "dark|light|none|unknown",
    "team_confidence": 0.0,
    "jersey_number": null,
    "jersey_number_confidence": 0.0
  }},

  "disc_motion": {{
    "moved_significantly": false,
    "direction": "left_to_right|right_to_left|top_to_bottom|bottom_to_top|diagonal_up_right|diagonal_up_left|diagonal_down_right|diagonal_down_left|mostly_stationary|unclear",
    "direction_confidence": 0.0
  }},

  "field_geometry": {{
    "endzone_near_visible": false,
    "endzone_near_x_norm": null,
    "endzone_far_visible": false,
    "endzone_far_x_norm": null,
    "sideline_left_visible": false,
    "sideline_right_visible": false,
    "geometry_confidence": 0.0
  }},

  "scoreboard": {{
    "visible": false,
    "dark_team_score": null,
    "light_team_score": null,
    "clock_text": null,
    "confidence": 0.0
  }},

  "events": {{
    "throw_release_observed": false,
    "throw_release_team": "dark|light|none|unknown",
    "throw_release_confidence": 0.0,
    "catch_completed_observed": false,
    "catch_team": "dark|light|none|unknown",
    "catch_completed_confidence": 0.0,
    "drop_observed": false,
    "drop_confidence": 0.0,
    "block_observed": false,
    "block_defender_team": "dark|light|none|unknown",
    "block_confidence": 0.0,
    "interception_observed": false,
    "interception_team": "dark|light|none|unknown",
    "interception_confidence": 0.0,
    "out_of_bounds_observed": false,
    "out_of_bounds_confidence": 0.0,
    "layout_observed": false,
    "layout_confidence": 0.0,
    "arms_raised_score_signal_observed": false,
    "arms_raised_count": 0,
    "arms_raised_score_signal_confidence": 0.0
  }},

  "formation": {{
    "phase": "pre_pull|pull_in_air|live_play|post_score_celebration|between_points|stoppage|unknown",
    "phase_confidence": 0.0,
    "pull_formation_visible": false
  }},

  "players": {{
    "dark_count_visible": 0,
    "light_count_visible": 0,
    "in_endzone_near": 0,
    "in_endzone_far": 0
  }},

  "text_observed": [
    {{"text": "string", "kind": "jersey|other", "confidence": 0.0}}
  ],

  "debug_note": "",
  "model": {{"provider": "gemini", "model_id": "gemini-2.5-flash", "version": "v0"}},
  "confidence_overall": 0.5,
  "raw_response_ref": null
}}


FIELD-BY-FIELD GUIDANCE
=======================

scene:
- field_visible: how much of the playing field is in this frame's view.
- camera: where the camera appears to be relative to the field.
- multiple_discs_possible: true if any disc-shaped object on the sideline could
  be confused for the active disc.

disc (current physical state of the disc):
- visible: did you see the disc at any point in this window's frames?
- visibility_quality: how clearly?
- in_air: is the disc airborne? (true even if briefly mid-flight)
- on_ground: is the disc resting on the ground without being held?
- held_by_player: is a player physically gripping the disc?
- state_confidence: how confident in the in_air/on_ground/held flags.
NOTE: in_air, on_ground, held_by_player describe orthogonal-ish physical states.
Pick whichever is most accurate for the LATEST visible disc state in this window.
If the disc transitions mid-window, pick the END state and ALSO set the matching
event flag (throw_release_observed for held->air, catch_completed_observed or
drop_observed for air->held/air->ground).

disc_position (where in the camera frame is the disc):
- x_norm: 0.0 = left edge of frame, 1.0 = right edge. Set to null if you can't
  reasonably ballpark.
- y_norm: 0.0 = top edge of frame, 1.0 = bottom edge. Same null rule.
- confidence: 0.0 if either coordinate is null.

disc_possessor (which team is in contact with the disc, if any):
- team: dark | light | none (no team in contact, e.g., disc is in flight) | unknown
- team_confidence: how confident in the team color call.
- jersey_number: the visible jersey number string of the player in contact, if
  legible. null if not legible. The VLM is not asked to infer player identity.
- jersey_number_confidence: 0 if jersey_number is null.

disc_motion (did the disc move within THIS window's frames):
- moved_significantly: true only if the disc visibly translated across the frame
  by a meaningful amount within the window. Stationary held disc = false.
- direction: pick the dominant direction of motion in-frame. "mostly_stationary"
  if held without much frame motion. "unclear" if motion is visible but direction
  is too ambiguous to call.
- direction_confidence: how confident.

field_geometry (where on screen are the field landmarks):
- endzone_near_visible / endzone_far_visible: an endzone closer to the camera
  is "near"; deeper into the frame is "far". For sideline cameras, both can be
  visible if the camera is centered. For endzone cameras, only one will be
  prominent.
- endzone_near_x_norm / endzone_far_x_norm: where in the frame (0=left, 1=right)
  is the endzone LINE visible. Null if not visible.
- sideline_left_visible / sideline_right_visible: are the side lines visible
  on the left/right side of the frame.
- geometry_confidence: how confident in these landmark calls.

scoreboard:
- visible: is a scoreboard / scorebug on screen?
- dark_team_score, light_team_score: integer scores if extractable.
- clock_text: the raw clock as displayed (e.g., "09:06"). Null if not visible.

events (per-window event flags — multiple may fire if the window straddles
events; each is a yes/no fact + confidence):

- throw_release_observed: true if the disc transitions from held -> in_air
  within this window. Set throw_release_team to the team that was holding
  the disc just before release.
- catch_completed_observed: true if the disc transitions from in_air -> held
  by a player of the SAME team that threw it. Set catch_team.
- drop_observed: true ONLY if the disc was airborne and then visibly hit the
  ground without being caught. Strict definition:
  * NOT a drop: a player laying out / diving and catching the disc successfully
  * NOT a drop: a player on the ground holding the disc after a successful catch
  * NOT a drop: a player picking up a disc that was already on the ground
  Set drop_observed=true ONLY when you see the disc fall from the air to the
  ground without being held. If you can't see the airborne phase or the failure
  to catch, leave drop_observed=false. Drops are RARE in actual gameplay
  (Ultimate's average completion rate is 85-95%); be conservative.
- block_observed: true if a defender visibly contacts the disc mid-flight
  (regardless of where the disc lands afterwards). Set block_defender_team.
- interception_observed: true if the disc transitions from in_air -> held by a
  player of the OPPOSITE team. Set interception_team to the team that caught it.
- out_of_bounds_observed: true if the disc clearly crossed a sideline or back
  endzone line.
- layout_observed: true if any player visibly dives full-body horizontally.
- arms_raised_score_signal_observed: true if anyone (player or sideline) has
  BOTH arms straight overhead — the WFDF "goal" signal. Set arms_raised_count
  to the number of distinct people doing this.

formation:
- phase: pick one (see system prompt for definitions).
  * IMPORTANT goal-detection cue: if you observe a player visibly catching
    or holding the disc INSIDE an endzone area (the rectangular zone behind
    an endzone line, painted on the field), set phase = post_score_celebration
    even if no celebratory arms-up is visible yet. The endzone catch IS
    the goal moment in WFDF Ultimate; the celebration is secondary.
  * If the LAST visible action in this window is a player holding the disc
    inside the endzone (their feet are inside the colored rectangle behind
    the endzone line), and the previous game state was live_play, this
    window IS a scoring moment.
- phase_confidence.
- pull_formation_visible: true ONLY if you see the 7-defenders-on-endzone
  formation explicitly.

players:
- dark_count_visible / light_count_visible: integer counts of players visible
  by jersey color.
- in_endzone_near / in_endzone_far: how many players (any team) are inside
  each visible endzone area.

text_observed:
- Free-form OCR for non-scoreboard text (jersey numbers in passing, sideline
  banners, etc). Scoreboard text goes in the dedicated scoreboard field above.
- kind: jersey | other.

debug_note:
- ONE short sentence flagging anything you observed that the schema doesn't
  capture, and might matter for debugging. The LLM IGNORES this. It is for
  human-in-the-loop diagnosis only.
- Examples: "Sun glare obscured the right half of the field" or "Two players
  appeared to be jumping for the same disc near the back endzone".
- Do NOT use this to insert claims like "this looks like a turnover" — those
  belong in the structured event fields.

confidence_overall:
- Aggregate confidence that this entire Observation is faithful to what was
  on screen.
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
