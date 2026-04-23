"""Staged point-boundary fusion detector for Phase 2."""

from __future__ import annotations

from statistics import mean

from sva.points.types import BoundarySignal, PointBoundaryCandidate, PointRecord


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


__all__ = ["detect_points"]
