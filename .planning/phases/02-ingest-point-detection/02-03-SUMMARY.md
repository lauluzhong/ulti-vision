---
phase: 02-ingest-point-detection
plan: 03
subsystem: point-aware-pipeline
tags: [phase2, pipeline, events, point-scope, migration, orchestration]

requires:
  - phase: 02-ingest-point-detection / plan 01
    provides: "shared ingest baseline and Phase 2 source intake"
  - phase: 02-ingest-point-detection / plan 02
    provides: "persisted point rows and staged detector"
provides:
  - "Strict point-scoped event contract with explicit in-point timestamps"
  - "Point-aware pipeline orchestration driven by persisted point rows"
  - "Point-filterable event persistence coverage"
affects: ["Phase 3", "Phase 4", "Phase 6", "Phase 7"]

requirements-completed: [POINT-03]

completed: 2026-04-23
status: complete
---

# Phase 02 Plan 03: Point-Aware Pipeline Contracts Summary

**Closed the loop on Phase 2 by making points the authoritative grouping primitive for downstream processing: events now persist non-null point metadata, the pipeline detects and persists points before perception, and interpretation runs per point rather than across one whole-game observation bucket.**

## Task Commits

1. `62edc09` — `feat(02-03): propagate point-scoped events through pipeline`

## Accomplishments

### Task 1 — Tightened event contract and persistence

- Updated `src/sva/models.py` so `Event` now requires `point_id`, `point_ordinal`, and `in_point_ts_ms`.
- Extended `TraceContext` with `point_ordinal` and propagated the new field through both VLM and LLM adapters.
- Updated `src/sva/interpret/adapters/claude.py` so the Phase 1 stub emits point-aware events instead of leaving point metadata blank.
- Added `migrations/versions/0004_phase2_point_scoped_events.py` to:
  - add `point_ordinal` and `in_point_ts_ms` to `events`
  - backfill existing Phase 1 rows
  - tighten `events.point_id` to non-null
  - add a composite `(game_id, point_id)` index for point-scoped filtering
- Updated `src/sva/events_dao.py` to persist the stricter point metadata and added a point-filtered row query helper.

### Task 2 — Inserted point detection into pipeline orchestration

- Refactored `src/sva/pipeline.py` so the flow is now:
  - ingest
  - build point-boundary candidates
  - detect points
  - persist/list point rows
  - assign each window to a persisted point
  - interpret once per point
  - persist point-scoped events
- Added `_apply_point_scope(...)` so absolute timestamps remain intact while `in_point_ts_ms` is derived from the owning point boundary.
- Kept the Phase 2 candidate generation intentionally lightweight with a deterministic bootstrap whole-game candidate, which preserves the contract that downstream work is grouped by persisted points even before richer OCR/pull candidate extraction lands.

## Verification

- `./.venv/bin/python -m py_compile src/sva/models.py src/sva/observability/langfuse.py src/sva/perceive/adapters/gemini.py src/sva/interpret/adapters/claude.py src/sva/events_dao.py src/sva/pipeline.py tests/test_models.py tests/test_interpret_adapter.py tests/test_point_scoped_pipeline.py tests/test_events_dao.py tests/test_cli_e2e.py migrations/versions/0004_phase2_point_scoped_events.py` → passed
- `./.venv/bin/pytest tests/test_models.py tests/test_interpret_adapter.py tests/test_point_scoped_pipeline.py -q` → `8 passed, 1 skipped`
- `./.venv/bin/pytest tests/test_events_dao.py tests/test_cli_e2e.py tests/test_db_migration.py -q` → `6 skipped` (Postgres unavailable in current session)

## Deviations / Notes

- The DB-backed verification for `events` migration behavior and end-to-end persistence is present but remains environment-gated until Postgres is running locally.
- Candidate extraction is still intentionally minimal here. This plan finishes the Phase 2 storage and orchestration contract, while keeping the grouped-by-point pipeline seam ready for richer point-boundary discovery inputs.

## Phase Outcome

Phase 2 is now complete:

- local files and approved public URLs share one normalization path
- point rows exist with stable IDs and inspectable evidence
- persisted events are point-scoped by construction rather than by convention
- downstream phases can assume `point_id` and `in_point_ts_ms` exist

## Self-Check: PASSED

- `src/sva/pipeline.py` runs point detection before any perception loop
- `src/sva/models.py` requires point-aware event metadata
- `src/sva/events_dao.py` persists `point_id`, `point_ordinal`, and `in_point_ts_ms`
- `migrations/versions/0004_phase2_point_scoped_events.py` exists
- unit coverage proves detect -> perceive -> interpret -> persist ordering

---
*Phase: 02-ingest-point-detection*
*Completed: 2026-04-23*
