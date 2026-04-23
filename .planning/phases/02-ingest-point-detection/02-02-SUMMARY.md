---
phase: 02-ingest-point-detection
plan: 02
subsystem: points
tags: [phase2, points, detector, dao, migration, staged-fusion]

requires:
  - phase: 02-ingest-point-detection / plan 01
    provides: "shared ingest baseline and Phase 2 source intake"
provides:
  - "First-class `points` persistence schema and DAO"
  - "Stable ordinal-based `point_id` generation"
  - "Staged OCR/pull/VLM fusion detector"
affects: ["02-03", "Phase 7"]

requirements-completed: [POINT-01]

completed: 2026-04-23
status: complete
---

# Phase 02 Plan 02: Point Detection & Persistence Summary

**Added the first-class point-boundary layer for Phase 2: persisted point rows plus a staged detector that treats scoreboard OCR and pull heuristics as primary signals and only uses VLM on ambiguous spans.**

## Task Commits

1. `9ae5b48` — `feat(02-02): add persisted point records`
2. `36256e6` — `feat(02-02): add staged point boundary detector`

## Accomplishments

### Task 1 — Points schema and DAO

- Added `src/sva/points/types.py` with explicit `BoundarySignal`, `PointBoundaryCandidate`, and `PointRecord` contracts.
- Added `src/sva/points/dao.py` with `PointRow`, `insert_points`, `list_points`, and `find_point_for_video_ts`.
- Added `src/sva/points/__init__.py` exports so later phases can consume the new point layer directly.
- Added migration `0003_phase2_points.py` creating the `points` table with stable `point_id`, `point_ordinal`, absolute start/end timestamps, confidence, and JSON boundary evidence.
- Added DB-gated DAO coverage in `tests/test_points_dao.py`.

### Task 2 — Staged detector

- Added `src/sva/points/detector.py` with a staged detector that:
  - prefers scoreboard and pull signals when they are confident
  - uses VLM only when a candidate span is ambiguous
  - refuses to let VLM act as a whole-game primary detector without a non-VLM anchor
- Added pure unit coverage in `tests/test_point_detection.py` proving both ordered emission and the VLM tie-break-only rule.

## Verification

- `./.venv/bin/pytest tests/test_point_detection.py tests/test_points_dao.py -q` → `2 passed, 1 skipped`
- `./.venv/bin/python -m py_compile src/sva/points/types.py src/sva/points/dao.py src/sva/points/detector.py src/sva/points/__init__.py` → passed

## Deviations / Notes

- The DAO test remains Postgres-gated, consistent with the rest of the repo’s DB integration tests.
- Point detection is intentionally bounded to structured candidates in this plan. The actual pipeline insertion happens in `02-03`, which keeps this wave focused on the point layer itself instead of mixing persistence and orchestration changes.

## Ready for Next Plan

Phase 2 can now move to `02-03`:
- point rows exist
- stable `point_id` semantics are defined
- the detector exists and is unit-tested
- the next step is propagating point assignment into events and the main pipeline

## Self-Check: PASSED

- `src/sva/points/types.py` exists
- `src/sva/points/dao.py` exists
- `src/sva/points/detector.py` exists
- `migrations/versions/0003_phase2_points.py` exists
- detector tests pass

---
*Phase: 02-ingest-point-detection*
*Completed: 2026-04-23*
