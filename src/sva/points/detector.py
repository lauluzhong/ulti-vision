"""Point-boundary detector — produces PointRecord rows from VLM observations.

Two entry points:

- `detect_points_from_observations(game_id, observations)` — v0 path. Walks
  observations chronologically, identifies contiguous in-point runs from the
  VLM-reported game phase, anchors each point to a pull formation or score
  signal when one is visible. Falls back to a single "unclear" point covering
  the whole video if the VLM never gives confident phase signals.

- `detect_points(game_id, candidates)` — legacy/manual path. Used by tests
  and by future OCR-fed candidate paths. Kept for backward compat.
"""

from __future__ import annotations

from statistics import mean

from sva.models import Observation
from sva.points.types import BoundarySignal, PointBoundaryCandidate, PointRecord

# Phases that count as "inside an active point" — pre-pull setup, the pull
# itself, contested play, and the brief score celebration before players walk
# back to lines.
IN_POINT_PHASES = frozenset({"pre_pull", "pull_in_air", "live_play", "post_score_celebration"})

# Phase confidence threshold below which we treat the phase as noise and carry
# over the prior classification. Avoids churning point boundaries on a single
# noisy window.
_PHASE_CONFIDENCE_FLOOR = 0.4

# When detect_points_from_observations falls back to a single "unclear" point
# covering the whole video, this confidence is reported on the point record so
# the UI can render a "needs review" badge.
_UNCLEAR_FALLBACK_CONFIDENCE = 0.10


def _stable_point_id(game_id: str, point_ordinal: int) -> str:
    return f"{game_id}:pt_{point_ordinal:03d}"


def _evidence_for_candidate(candidate: PointBoundaryCandidate) -> list[BoundarySignal]:
    evidence: list[BoundarySignal] = []
    if candidate.scoreboard is not None and candidate.scoreboard.confidence >= 0.5:
        evidence.append(candidate.scoreboard)
    if candidate.pull is not None and candidate.pull.confidence >= 0.4:
        evidence.append(candidate.pull)
    if candidate.requires_vlm_tiebreak() and candidate.vlm is not None and candidate.vlm.confidence >= 0.5:
        evidence.append(candidate.vlm)
    return evidence


def detect_points(game_id: str, candidates: list[PointBoundaryCandidate]) -> list[PointRecord]:
    """Produce ordered point records from staged OCR/heuristic/VLM fusion candidates."""
    detected: list[PointRecord] = []
    for ordinal, candidate in enumerate(sorted(candidates, key=lambda item: item.start_video_ts_ms), start=1):
        if not candidate.has_non_vlm_anchor():
            continue
        evidence = _evidence_for_candidate(candidate)
        if not evidence:
            continue
        detected.append(
            PointRecord(
                point_id=_stable_point_id(game_id, ordinal),
                game_id=game_id,
                point_ordinal=ordinal,
                start_video_ts_ms=candidate.start_video_ts_ms,
                end_video_ts_ms=candidate.end_video_ts_ms,
                confidence=round(mean(signal.confidence for signal in evidence), 3),
                boundary_evidence=evidence,
            )
        )
    return detected


def _classify(obs: Observation, prev: str) -> str:
    """Return 'in_point' or 'between' for one observation, with carry-over for noise."""
    phase = obs.formation.phase
    confidence = obs.formation.phase_confidence

    if phase in IN_POINT_PHASES and confidence >= _PHASE_CONFIDENCE_FLOOR:
        return "in_point"
    if phase == "between_points" and confidence >= _PHASE_CONFIDENCE_FLOOR:
        return "between"

    # Unknown / stoppage / low-confidence — carry over so single noisy windows
    # don't fragment a point.
    return prev


def _signals_for_run(observations: list[Observation]) -> list[BoundarySignal]:
    """Collect VLM-observed pull and score signals from a contiguous in-point run.

    v2.0 schema: pull formation lives on `obs.formation.pull_formation_visible`,
    arms-up score signals live on `obs.events.arms_raised_score_signal_observed`,
    scoreboard ticks are inferred from successive ScoreboardReading values
    elsewhere (the LLM, not this detector).
    """
    signals: list[BoundarySignal] = []
    for obs in observations:
        f = obs.formation
        ev = obs.events
        if f.pull_formation_visible:
            signals.append(
                BoundarySignal(
                    source="pull",
                    video_ts_ms=obs.video_ts_start_ms,
                    confidence=max(f.phase_confidence, 0.4),
                    details={
                        "phase": f.phase,
                        "evidence": "vlm_observed_pull_formation",
                        "window_id": obs.window_id,
                    },
                )
            )
        if ev.arms_raised_score_signal_observed and ev.arms_raised_score_signal_confidence > 0.0:
            signals.append(
                BoundarySignal(
                    source="vlm",
                    video_ts_ms=obs.video_ts_end_ms,
                    confidence=ev.arms_raised_score_signal_confidence,
                    details={
                        "score_signal": "arms_raised",
                        "arms_raised_count": ev.arms_raised_count,
                        "window_id": obs.window_id,
                    },
                )
            )
    return signals


def _build_point_from_run(
    game_id: str,
    ordinal: int,
    run: list[Observation],
) -> PointRecord:
    """Construct a PointRecord from a contiguous in-point observation run."""
    start_ms = run[0].video_ts_start_ms
    end_ms = run[-1].video_ts_end_ms
    signals = _signals_for_run(run)
    confidence = (
        round(mean(signal.confidence for signal in signals), 3)
        if signals
        else round(mean(obs.formation.phase_confidence for obs in run), 3)
    )
    return PointRecord(
        point_id=_stable_point_id(game_id, ordinal),
        game_id=game_id,
        point_ordinal=ordinal,
        start_video_ts_ms=start_ms,
        end_video_ts_ms=end_ms,
        confidence=confidence,
        boundary_evidence=signals,
    )


def _unclear_fallback(game_id: str, observations: list[Observation]) -> list[PointRecord]:
    """When the VLM never gave confident phase signals, treat the whole video as one
    'unclear' point so the user can manually edit boundaries via the Phase 7 editor.
    """
    if not observations:
        return []
    return [
        PointRecord(
            point_id=_stable_point_id(game_id, 1),
            game_id=game_id,
            point_ordinal=1,
            start_video_ts_ms=observations[0].video_ts_start_ms,
            end_video_ts_ms=observations[-1].video_ts_end_ms,
            confidence=_UNCLEAR_FALLBACK_CONFIDENCE,
            boundary_evidence=[
                BoundarySignal(
                    source="vlm",
                    video_ts_ms=observations[0].video_ts_start_ms,
                    confidence=_UNCLEAR_FALLBACK_CONFIDENCE,
                    details={
                        "evidence": "no_confident_phase_signals",
                        "fallback": "single_point_unclear_whole_video",
                        "window_count": len(observations),
                    },
                )
            ],
        )
    ]


def detect_points_from_observations(
    game_id: str,
    observations: list[Observation],
) -> list[PointRecord]:
    """v0 entry point: produce point boundaries directly from VLM observations.

    Walks the observation timeline, identifies contiguous in-point runs based
    on the VLM-reported game phase, anchors each point to whatever pull or
    score signals the VLM saw inside that run.

    Returns:
        - Ordered list of PointRecord, one per detected point.
        - On insufficient signal: a single "unclear" PointRecord covering the
          whole video, low confidence, so the UI can prompt for manual edit.
        - On empty input: empty list.
    """
    if not observations:
        return []

    sorted_obs = sorted(observations, key=lambda o: o.video_ts_start_ms)
    runs: list[list[Observation]] = []
    current_run: list[Observation] = []
    classification = "between"

    for obs in sorted_obs:
        new_class = _classify(obs, classification)
        if new_class == "in_point":
            current_run.append(obs)
        else:
            if current_run:
                runs.append(current_run)
                current_run = []
        classification = new_class

    if current_run:
        runs.append(current_run)

    if not runs:
        return _unclear_fallback(game_id, sorted_obs)

    return [
        _build_point_from_run(game_id, ordinal, run)
        for ordinal, run in enumerate(runs, start=1)
    ]


__all__ = ["detect_points", "detect_points_from_observations", "IN_POINT_PHASES"]
