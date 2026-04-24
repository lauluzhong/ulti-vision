---
phase: 06-async-orchestration-and-api
plan: 03
subsystem: canonical-events-and-corrections-api
tags: [phase6, api, events, corrections, memory]

requires:
  - phase: 06-async-orchestration-and-api / plan 02
    provides: "stable async API composition root and persisted job-status surface"
provides:
  - "Canonical `GET /games/{game_id}/events` filtering over stored rows"
  - "Append-only `POST /games/{game_id}/corrections` over the Phase 5 memory substrate"
  - "Thin correction orchestration seam for later UI writes"
affects: ["06-04", "Phase 7"]

requirements-completed:
  - API-03
  - API-04

completed: 2026-04-25
status: complete
---

# Phase 06 Plan 03: Canonical Events API and Corrections Submission Summary

**Added the first real game-facing read/write surface on top of canonical persisted data: filterable event timeline reads and append-only coach corrections that compound into memory.**

## Accomplishments

### Task 1 — Canonical events read surface

- Updated [src/sva/api/app.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/api/app.py) with `GET /games/{game_id}/events`.
- Expanded [src/sva/api/contracts.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/api/contracts.py) with stable response models for canonical timeline reads.
- The route now:
  - checks that the game exists via the canonical job row
  - reads only persisted events through [src/sva/events_dao.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/events_dao.py)
  - supports `point_id`, `event_type`, and `team` filters without recomputation

### Task 2 — Append-only corrections write path

- Added [src/sva/memory/service.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/memory/service.py) as the thin Phase 6 correction orchestration seam.
- Updated [src/sva/api/app.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/api/app.py) with `POST /games/{game_id}/corrections`.
- The write path now:
  - validates correction payload shape up front
  - persists immutable correction rows through the existing Phase 5 DAO
  - derives coach-scoped memory rows through the existing writer
  - avoids mutating canonical event rows in place

### Task 3 — Route coverage and regression guardrails

- Added [tests/test_events_api.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/tests/test_events_api.py) to prove canonical ordering, filter pass-through, and unknown-game handling.
- Added [tests/test_corrections_api.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/tests/test_corrections_api.py) to prove immutable correction acceptance, coach provenance capture, and invalid-payload rejection before the service runs.
- Updated [src/sva/memory/__init__.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/memory/__init__.py) to expose the new service seam cleanly.

## Verification

- `./.venv/bin/python -m py_compile src/sva/api/app.py src/sva/api/contracts.py src/sva/memory/service.py tests/test_events_api.py tests/test_corrections_api.py` → passed
- `./.venv/bin/pytest tests/test_events_api.py tests/test_corrections_api.py -q` → `6 passed`
- `./.venv/bin/pytest tests/test_ingest_api.py tests/test_jobs_api.py tests/test_events_api.py tests/test_corrections_api.py tests/test_memory_writer.py -q` → `15 passed`

## Deviations / Notes

- The correction route keeps the existing Phase 5 schema contracts intact by wrapping them instead of inventing a second correction model.
- Source event lookup is validated against canonical persisted rows for the target point before derived memory is written.

## Ready for Next Plan

Phase 6 now moves to:

- `06-04` CSV export and crash-resume verification

## Self-Check: PASSED

- event reads are canonical and filterable
- corrections remain append-only and coach-provenance aware
- Phase 5 memory contracts were reused rather than reopened

---
*Phase: 06-async-orchestration-and-api*
*Completed: 2026-04-25*
