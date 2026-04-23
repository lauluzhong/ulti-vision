---
phase: 03-perception-layer
plan: 01
subsystem: observations-cache-backbone
tags: [phase3, observations, cache, dao, migration, schema]

requires:
  - phase: 02-ingest-point-detection / plan 03
    provides: "point-aware pipeline seam and non-null point metadata"
provides:
  - "First-class observations persistence schema"
  - "Exact-triple cache-key DAO helpers"
  - "Observation schema refinements for ambiguity handling"
affects: ["03-02", "03-03", "Phase 4"]

requirements-completed: []

completed: 2026-04-23
status: complete
---

# Phase 03 Plan 01: Observations Persistence & Cache Contract Summary

**Established the Phase 3 storage backbone by turning observations into a first-class persisted artifact with an exact `(video_id, window_id, prompt_version_hash)` cache contract, while refining the canonical Observation schema for the ambiguity cases already identified in project research.**

## Task Commits

1. `2dfa886` — `feat(03-01): add observation persistence cache backbone`

## Accomplishments

### Task 1 — Observation schema and observations table contract

- Refined `src/sva/models.py` with structured perception ambiguity fields:
  - `DiscObservation.visibility_quality`
  - `SceneObservation.multiple_discs_possible`
- Added `migrations/versions/0005_phase3_observations.py` creating the `observations` table with:
  - `observation_id`
  - `game_id`
  - `point_id`
  - `point_ordinal`
  - `video_id`
  - `window_id`
  - `prompt_version_hash`
  - observation/video timestamps
  - `confidence_overall`
  - `schema_version`
  - `raw_response_ref`
  - canonical payload JSONB
- Added cache-key and lookup indexes, including the exact-triple cache index on `(video_id, window_id, prompt_version_hash)`.

### Task 2 — Observation DAO and DB-gated persistence coverage

- Added `src/sva/observations_dao.py` with:
  - `ObservationRow`
  - `insert_observations(...)`
  - `list_cached_observations(...)`
- Extended `src/sva/perceive/__init__.py` exports so later plans can consume the observation DAO helpers directly.
- Added `tests/test_observations_dao.py` proving persisted observations round-trip by the exact-triple cache key.
- Extended `tests/test_db_migration.py` so head-state migrations assert the `observations` table exists.
- Extended `tests/test_models.py` so the refined Observation ambiguity defaults are locked by tests.

## Verification

- `./.venv/bin/python -m py_compile src/sva/models.py src/sva/observations_dao.py src/sva/perceive/__init__.py tests/test_models.py tests/test_observations_dao.py tests/test_db_migration.py migrations/versions/0005_phase3_observations.py` → passed
- `./.venv/bin/pytest tests/test_models.py -q` → `7 passed`
- `./.venv/bin/pytest tests/test_observations_dao.py tests/test_db_migration.py -q` → `6 skipped` (Postgres unavailable in current session)

## Deviations / Notes

- The cache lookup seam in `run_window(...)` remains Plan `03-03` work. This plan intentionally landed the storage contract first so runner ownership is clean and unambiguous in the later integration step.
- DB-backed verification is ready but still environment-gated until Postgres is running locally.

## Ready for Next Plan

Phase 3 can now move into `03-02`:

- the canonical observation contract now covers ambiguity better
- the persistence schema exists for cache-backed perception
- the next dependency is the real Gemini adapter and richer perception observability, not more storage scaffolding

## Self-Check: PASSED

- `src/sva/observations_dao.py` exists
- `migrations/versions/0005_phase3_observations.py` exists
- exact-triple cache lookup exists
- Observation schema refinements are test-locked

---
*Phase: 03-perception-layer*
*Completed: 2026-04-23*
