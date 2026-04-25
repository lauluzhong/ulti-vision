---
phase: 07-evaluation-harness-and-alpha-ui
plan: 03
subsystem: point-boundary-api-and-rebucketing
tags: [phase7, points, api, rebucketing]

requires:
  - phase: 06-async-orchestration-and-api / plan 03
    provides: "canonical event API over stored event rows"
provides:
  - "List/update point-boundary API for coach edits"
  - "Transactional rebucketing of stored events and observations"
  - "Guardrail preventing stale correction/memory provenance after boundary edits"
affects: ["Phase 2", "Phase 7"]

requirements-completed:
  - POINT-02

completed: 2026-04-25
status: complete
---

# Phase 07 Plan 03: Point-Boundary API and Rebucketing Summary

**Added the real backend contract for coach-edited point boundaries: list current points, replace the full boundary set, and rebucket canonical stored rows in one service path.**

## Accomplishments

### Task 1 — API contracts and routes

- Added point-boundary request/response models in [src/sva/api/contracts.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/api/contracts.py).
- Added:
  - `GET /games/{game_id}/points`
  - `PUT /games/{game_id}/points`
  in [src/sva/api/app.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/api/app.py)

### Task 2 — Centralized rebucketing service

- Added [src/sva/points/service.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/points/service.py) to:
  - validate ordered, non-overlapping boundaries
  - regenerate stable point ids/ordinals
  - rebucket stored events by `video_ts_ms`
  - rebucket stored observations by `observation_ts_ms`

### Task 3 — Provenance guardrail

- Extended point signal sources with `"manual"` in [src/sva/points/types.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/points/types.py).
- Hard-blocked boundary edits once corrections already exist for the game, preventing stale correction and memory provenance from being silently left behind.

### Task 4 — Verification coverage

- Added [tests/test_points_api.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/tests/test_points_api.py)
- Added [tests/test_point_rebucket_service.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/tests/test_point_rebucket_service.py)

## Verification

- `./.venv/bin/python -m py_compile src/sva/points/types.py src/sva/points/service.py src/sva/api/contracts.py src/sva/api/app.py tests/test_points_api.py tests/test_point_rebucket_service.py` → passed
- `./.venv/bin/pytest tests/test_points_api.py tests/test_point_rebucket_service.py -q` → `6 passed`

## Deviations / Notes

- The service rebuckets stored rows without re-running interpretation. That keeps the edit path fast and deterministic for alpha while preserving the explicit “edit boundaries before corrections” rule.

## Ready for Next Plan

- `07-05` correction UI and point-boundary editor

---
*Phase: 07-evaluation-harness-and-alpha-ui*
*Completed: 2026-04-25*
