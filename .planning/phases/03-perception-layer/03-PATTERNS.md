# Phase 3: Perception Layer - Patterns

## Purpose

This file maps the current repo’s concrete implementation patterns to the work Phase 3 needs, so the planner can extend existing seams instead of inventing new ones.

## File-Level Analogs

### Adapter growth pattern

**Best analog:** `src/sva/interpret/adapters/claude.py`

Why it matters:
- It already shows the project’s preferred “stub first, real adapter later” shape.
- It wraps the provider call in `@observe_call(...)`.
- It returns the canonical model (`Event`) instead of leaking provider response structure.

What to copy for Phase 3:
- Keep `src/sva/perceive/adapters/gemini.py` as the single-file provider implementation.
- Preserve the wrapper pattern: provider-specific helper returns `(result, cost, tokens, ctx)` and `observe_call` handles tracing/cost persistence.
- Keep `make_default_perceiver()` as the only swap point.

### Persistence + DAO pattern

**Best analogs:** `src/sva/events_dao.py`, `src/sva/points/dao.py`

Why they matter:
- The repo uses small SQLAlchemy ORM mappings plus narrow helper functions.
- Migrations define schema; DAOs expose focused insert/list/query helpers.
- DB-gated tests validate persistence without dragging the whole pipeline into every test.

What to copy for Phase 3:
- Create an `observations` DAO with:
  - ORM row type
  - insert helper(s)
  - cache-key lookup helper by `(video_id, window_id, prompt_version_hash)`
  - list/query helpers only where Phase 3 needs them
- Add a matching Alembic migration in the same style as `0003_phase2_points.py` and `0004_phase2_point_scoped_events.py`.

### Cache-before-expensive-work pattern

**Current closest analog:** `src/sva/pipeline.py`

Why it matters:
- `run_pipeline()` is already the stage-assembly point for ingest -> points -> perceive -> interpret -> persist.
- Phase 2 turned point rows into the authoritative grouping primitive before downstream work.

What to copy for Phase 3:
- Insert the observation cache check at the stage boundary before invoking the actual Gemini adapter.
- Keep the stage ordering explicit:
  - resolve point-owned window
  - lookup cached observations
  - if miss: invoke `run_window(...)`
  - persist observations
  - only then continue toward interpret

### Observability + cost recording pattern

**Best analogs:** `src/sva/observability/langfuse.py`, `src/sva/observability/cost.py`

Why they matter:
- They already encode the project’s instrumentation contract.
- `TraceContext` is the shared surface for `game_id`, `video_id`, `window_id`, `point_id`, and prompt hash.
- Cost recording already updates `jobs.cost_usd`.

What to copy for Phase 3:
- Extend, don’t replace, `TraceContext`.
- Keep latency/cost tied to the wrapped call rather than scattered through the pipeline.
- If cache hits need observability, add an explicit trace/metadata path without double-recording provider cost.

### Test layering pattern

**Best analogs:** `tests/test_swap_safe_contract.py`, `tests/test_perceive_adapter.py`, `tests/test_points_dao.py`, `tests/test_point_scoped_pipeline.py`

Why they matter:
- The repo already has a stable split between:
  - pure unit tests for contract and orchestration logic
  - DB-gated tests for persistence
  - thin integration tests for pipeline stage ordering

What to copy for Phase 3:
- Contract tests for any Observation schema refinements
- DB-gated cache/persistence tests for observation rows
- runner/pipeline tests that prove cache hit skips provider invocation
- keep heavy integration coverage focused on the stage boundary rather than duplicating provider behavior everywhere

## Exact Reuse Opportunities

### `src/sva/perceive/runner.py`

Use as the home for:
- cache lookup before provider call
- future “return cached observations” branch
- preserving the swap-safe `Perceiver` protocol entrypoint

### `src/sva/perceive/adapters/base.py`

Use as the canonical input contract for the perceiver. If Phase 3 needs more window metadata, prefer extending `PerceiveWindow` here rather than adding parallel ad hoc argument lists.

### `src/sva/models.py`

Use as the single place for Observation schema evolution. Follow the same pattern used for `Event` in Phase 2:
- evolve the canonical model first
- then update persistence and tests in lockstep

### `migrations/versions/0003_phase2_points.py` and `0004_phase2_point_scoped_events.py`

Use as migration style references:
- explicit typed columns
- additive upgrade path
- backfill before tightening constraints if needed
- narrow, phase-scoped schema changes

## Suggested Phase 3 File Targets

Based on the current repo shape, the likely Phase 3 write set should stay close to:

- `src/sva/models.py`
- `src/sva/perceive/adapters/gemini.py`
- `src/sva/perceive/runner.py`
- `src/sva/ingest/sampler.py`
- `src/sva/pipeline.py`
- `src/sva/observability/langfuse.py`
- `migrations/versions/0005_phase3_observations.py` (or the next numbered migration)
- `src/sva/observations_dao.py` or `src/sva/perceive/dao.py`
- new tests for observations persistence / cache / runner / pipeline reuse

## Planning Notes

- Prefer a dedicated observations DAO module over burying observation persistence inside `gemini.py` or `pipeline.py`.
- Keep the cache key explicit in storage and tests; do not infer it indirectly from opaque JSON.
- Follow the repo’s current convention of phase-by-phase tightening: land the storage seam first, then the real adapter, then the integration proof.

---
*Phase: 03-perception-layer*
*Pattern map prepared: 2026-04-23*
