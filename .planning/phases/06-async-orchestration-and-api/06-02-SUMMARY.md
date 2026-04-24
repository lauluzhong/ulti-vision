---
phase: 06-async-orchestration-and-api
plan: 02
subsystem: async-submission-polling-and-queue-wiring
tags: [phase6, api, jobs, queue, polling]

requires:
  - phase: 06-async-orchestration-and-api / plan 01
    provides: "durable queued jobs, persisted progress truth, and resume-safe orchestration"
provides:
  - "Async `POST /ingest` submission returning durable job metadata"
  - "Polling-first `GET /jobs/{job_id}` backed by persisted job state"
  - "Thin Dramatiq/Redis transport wrapper and matching local runtime config"
affects: ["06-03", "06-04", "Phase 7"]

requirements-completed:
  - API-01
  - API-02

completed: 2026-04-25
status: complete
---

# Phase 06 Plan 02: Async Submission, Polling API, and Queue Wiring Summary

**Converted the API surface from blocking ingest to durable async submission, exposed polling over canonical persisted job state, and wired the thin queue/runtime seam that later UI work will call.**

## Accomplishments

### Task 1 — Async submission surface

- Updated [src/sva/api/app.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/api/app.py) so `POST /ingest` now:
  - preserves the existing one-source and rights-ack validation behavior
  - creates a durable queued job row through `submit_local_job(...)` or `submit_remote_job(...)`
  - enqueues the job instead of executing the full pipeline inline
  - returns `202 Accepted` with stable job metadata via [src/sva/api/contracts.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/api/contracts.py)
- Added [src/sva/queue.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/queue.py) as a thin Dramatiq wrapper around the existing orchestration service.

### Task 2 — Polling-first status surface

- Added `GET /jobs/{job_id}` in [src/sva/api/app.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/api/app.py), backed by canonical persisted job state from [src/sva/jobs_dao.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/jobs_dao.py).
- Added [tests/test_jobs_api.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/tests/test_jobs_api.py) to prove:
  - persisted running status is serialized cleanly
  - partial point/window counts are returned from DB-backed progress
  - unknown jobs fail with 404 instead of inventing queue-derived state

### Task 3 — Runtime configuration and route coverage

- Updated [src/sva/config.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/config.py) with `REDIS_URL`.
- Updated [pyproject.toml](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/pyproject.toml) to include `dramatiq` and `redis`.
- Updated [.env.example](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/.env.example) and [docker-compose.yml](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/docker-compose.yml) so the local dev runtime matches the new queue transport.
- Updated [tests/test_ingest_api.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/tests/test_ingest_api.py) for async submission semantics.

## Verification

- `./.venv/bin/python -m py_compile src/sva/api/app.py src/sva/api/contracts.py src/sva/queue.py src/sva/config.py tests/test_ingest_api.py tests/test_jobs_api.py` → passed
- `./.venv/bin/pytest tests/test_ingest_api.py tests/test_jobs_api.py -q` → `5 passed`

## Deviations / Notes

- `uv.lock` was already user-modified in the worktree, so this plan intentionally did not rewrite or stage it.
- The status route currently exposes canonical stage plus aggregate partial progress counts from the persisted `jobs.progress` payload, which is enough for the Phase 7 polling UI baseline without inventing broker-owned truth.

## Ready for Next Plan

Phase 6 now moves to:

- `06-03` canonical events API and corrections submission

## Self-Check: PASSED

- submission no longer blocks on pipeline execution
- polling reads canonical persisted state rather than queue internals
- queue transport stays a thin wrapper over normal Python orchestration

---
*Phase: 06-async-orchestration-and-api*
*Completed: 2026-04-25*
