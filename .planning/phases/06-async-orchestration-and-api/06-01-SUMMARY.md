---
phase: 06-async-orchestration-and-api
plan: 01
subsystem: durable-job-lifecycle-and-orchestration-substrate
tags: [phase6, jobs, orchestration, resume-safety, api-foundation]

requires:
  - phase: 05-memory-correction-loop / plan 04
    provides: "completed persisted memory substrate and honest Phase 5 baseline"
provides:
  - "Queued/pre-ingest jobs are first-class persisted rows"
  - "Resume-safe orchestration service with persisted stage/progress truth"
  - "Migration and service-level coverage for the new job lifecycle surface"
affects: ["06-02", "06-03", "06-04", "Phase 7"]

requirements-completed:
  - API-01
  - API-02

completed: 2026-04-25
status: complete
---

# Phase 06 Plan 01: Durable Job Lifecycle & Orchestration Substrate Summary

**Laid the real backend foundation for async Phase 6 work by making queued jobs legal before ingest, persisting stage/progress truth on `jobs`, and adding a resume-safe orchestration service that skips already-finished point work.**

## Task Commits

1. `d0af1d0` — `feat(06-01): add durable job lifecycle substrate`

## Accomplishments

### Task 1 — Canonical job lifecycle and persisted progress

- Added [src/sva/jobs_dao.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/jobs_dao.py) with:
  - `JobRow`
  - `JobRecord`
  - `get_job(...)`
  - `upsert_job(...)`
- Added [0009_phase6_job_progress.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/migrations/versions/0009_phase6_job_progress.py) to:
  - make `jobs.video_id` nullable for queued pre-ingest jobs
  - add `stage`, `progress`, and `error_message` to the jobs table
- Updated [tests/test_db_migration.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/tests/test_db_migration.py) so the migration smoke suite asserts the new Phase 6 job columns.

### Task 2 — Resume-safe orchestration service

- Added [src/sva/jobs_service.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/jobs_service.py) with:
  - `submit_local_job(...)`
  - `submit_remote_job(...)`
  - `process_job(...)`
- Updated [src/sva/ingest/ingest.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/ingest/ingest.py) so ingest now upserts the canonical job row and can rebuild an `IngestResult` from persisted job metadata for resume flows.
- Updated [src/sva/ingest/__init__.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/ingest/__init__.py) to export the new resume helper.

### Task 3 — Service-level verification of skip/reuse behavior

- Added [tests/test_jobs_service.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/tests/test_jobs_service.py) to prove:
  - local submission creates queued job state
  - `process_job(...)` skips points that already have persisted events
  - stage/progress truth is updated through ingest -> point_detect -> perceive -> interpret -> persist -> complete

## Verification

- `./.venv/bin/python -m py_compile src/sva/jobs_dao.py src/sva/ingest/ingest.py src/sva/jobs_service.py migrations/versions/0009_phase6_job_progress.py tests/test_jobs_service.py` → passed
- `./.venv/bin/pytest tests/test_jobs_service.py tests/test_db_migration.py tests/test_point_scoped_pipeline.py -q` → `3 passed, 9 skipped`

## Deviations / Notes

- This plan intentionally stopped at the durable orchestration substrate. The queue/worker transport wiring stays in `06-02`, where the updated Phase 6 plan set now calls it out explicitly.
- Progress truth currently lives on the canonical `jobs` row, which is enough for the polling-first Phase 6 API surface and keeps the status source single-store and inspectable.

## Ready for Next Plan

Phase 6 now moves to:

- `06-02` async submission/status API and thin queue wiring

## Self-Check: PASSED

- queued jobs now exist before ingest starts
- stage/progress truth is persisted instead of implied
- resume-safe orchestration uses persisted point/event state
- the backend is ready for async route and worker wiring

---
*Phase: 06-async-orchestration-and-api*
*Completed: 2026-04-25*
