---
phase: 03-perception-layer
plan: 03
subsystem: cache-first-perception-runner
tags: [phase3, sampler, runner, cache, pipeline, observability]

requires:
  - phase: 03-perception-layer / plan 01
    provides: "Observation persistence contract and exact-triple cache key"
  - phase: 03-perception-layer / plan 02
    provides: "Real Gemini adapter and prompt-hash observability seam"
provides:
  - "Validated 1-3 fps perception sampling envelope"
  - "Cache-first run_window path keyed by (video_id, window_id, prompt_version_hash)"
  - "Point-aware pipeline persistence before interpretation with cache-hit reuse"
affects: ["Phase 4", "Phase 6", "Phase 7"]

requirements-completed:
  - PERCEIVE-01
  - PERCEIVE-03

completed: 2026-04-23
status: complete
---

# Phase 03 Plan 03: Point-Aware Pipeline Cache Integration Summary

**Completed the Phase 3 join step by turning sampler fps into a real control surface, making `run_window(...)` cache-first, and proving the point-aware pipeline reuses persisted observations on reruns instead of re-paying Gemini cost.**

## Task Commits

1. `d3650ef` — `feat(03-03): add cache-first perception pipeline`

## Accomplishments

### Task 1 — One sampler control surface with deterministic window identity

- Reworked `src/sva/ingest/sampler.py` so `fps` now materially controls emitted windows instead of being ignored.
- Locked the v1 sampling envelope to `1 <= fps <= 3` with a clear fast-fail validation error for out-of-range requests.
- Added deterministic `make_window_id(...)` generation so reruns at the same fps preserve stable cache identities and fps changes do not collide.
- Updated the live CLI pipeline entrypoint so `sva ingest --fps ...` now actually flows through to `run_pipeline(...)`.

### Task 2 — Cache-first runner and point-aware pipeline reuse proof

- Extended `src/sva/perceive/runner.py` so `run_window(...)`:
  - computes the cache-facing prompt hash before provider invocation when the perceiver exposes that seam
  - checks Postgres-backed observation cache state first
  - returns cached canonical `Observation` payloads on a hit
  - emits a cache-hit observability trace instead of silently bypassing the perception layer
- Updated `src/sva/pipeline.py` so miss-path observations are persisted immediately before interpretation, while point ownership still comes from the Phase 2 persisted point rows.
- Added targeted verification files:
  - `tests/test_sampler.py`
  - `tests/test_perceive_runner.py`
- Extended:
  - `tests/test_point_scoped_pipeline.py`
  - `tests/test_observability.py`

## Verification

- `./.venv/bin/python -m py_compile src/sva/ingest/sampler.py src/sva/perceive/runner.py src/sva/pipeline.py src/sva/cli.py tests/test_sampler.py tests/test_perceive_runner.py tests/test_point_scoped_pipeline.py tests/test_observability.py` → passed
- `./.venv/bin/pytest tests/test_sampler.py -q` → `7 passed`
- `./.venv/bin/pytest tests/test_perceive_runner.py tests/test_point_scoped_pipeline.py tests/test_observability.py -q` → `8 passed, 2 skipped`
- Additional regression pass:
  - `./.venv/bin/pytest tests/test_swap_safe_contract.py tests/test_perceive_adapter.py -q` → `5 passed, 1 skipped`
  - `./.venv/bin/pytest tests/test_cli_e2e.py -q` → `1 skipped`

## Deviations / Notes

- Cache reuse is now proven at the runner/pipeline seam when `video_id`, `window_id`, and `prompt_version_hash` are stable across reruns. Broader cross-ingest identity stability is still downstream work, not a blocker for Phase 3’s architectural contract.
- Cache-hit observability is recorded as a cache-hit trace rather than a duplicate provider trace, preserving the “zero duplicate Gemini calls for the same triple” requirement.

## Ready for Next Phase

Phase 3 is now complete, and the next GSD move is Phase 4 discuss/plan:

- perception is real rather than stubbed
- expensive reruns are now cache-gated
- downstream interpretation can assume point-scoped, persisted observations as a stable upstream contract

## Self-Check: PASSED

- fps is now validated and affects sampling
- cached observations bypass provider invocation
- point-aware pipeline persists on miss and reuses on rerun
- swap-safe perceiver contract still holds

---
*Phase: 03-perception-layer*
*Completed: 2026-04-23*
