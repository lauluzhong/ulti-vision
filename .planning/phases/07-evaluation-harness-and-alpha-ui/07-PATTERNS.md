---
phase: 07-evaluation-harness-and-alpha-ui
type: patterns
created: 2026-04-25
updated: 2026-04-25
---

# Phase 07 Patterns

## Closest Existing Patterns

- API route composition:
  - `src/sva/api/app.py`
  - `src/sva/api/contracts.py`
  - analog for new points/video/eval-adjacent routes

- Thin orchestration seam over existing DAOs:
  - `src/sva/memory/service.py`
  - analog for `src/sva/points/service.py` and any eval gate service seam

- Canonical persisted reads:
  - `src/sva/events_dao.py`
  - `src/sva/points/dao.py`
  - analog for eval predicted-event loading and rebucketing

- Job orchestration and resume semantics:
  - `src/sva/jobs_service.py`
  - analog for point-boundary lifecycle hooks and later finalize/reprocess flow

- Route-level API tests:
  - `tests/test_ingest_api.py`
  - `tests/test_jobs_api.py`
  - `tests/test_events_api.py`
  - `tests/test_corrections_api.py`
  - `tests/test_exports_api.py`

- Service-level orchestration tests:
  - `tests/test_jobs_service.py`
  - `tests/test_orchestration.py`

## New Pattern Decisions

- `src/sva/eval/` becomes a new pure-Python package peer to the pipeline packages.
- `apps/web/` is a fresh frontend workspace because no reusable frontend patterns exist in the repo.
- Point rebucketing should update canonical stored event scope from persisted timestamps rather than inventing a parallel UI-only event model.
