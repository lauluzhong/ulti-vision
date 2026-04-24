# Phase 6: Async Orchestration & API - Context

**Gathered:** 2026-04-24
**Status:** Ready for research and planning
**Source:** GSD auto-resume continuation from completed Phase 5

<domain>
## Phase Boundary

Phase 6 turns the current synchronous CLI pipeline into a durable job workflow behind a real HTTP API. It is responsible for enqueueing work, exposing job status and partial results, preserving resume-safe execution, wiring the public correction endpoint onto the existing Phase 5 correction/memory substrate, and exporting canonical event rows as a stable CSV.

This phase is about orchestration and service surfaces. It does **not** build the alpha UI, point-boundary editor UX, or evaluation harness gates. It may create the backend seams those later phases depend on, but it should keep the API thin and reuse the existing canonical ingest, point, observation, event, and memory contracts instead of inventing a parallel data path.

</domain>

<decisions>
## Implementation Decisions

### Orchestration and durability
- **D-01:** Phase 6 owns the shift from `run_pipeline(...)` as a synchronous CLI entrypoint to a durable workflow that can be triggered from HTTP and resumed safely after interruption.
- **D-02:** Resume truth comes from persisted repo state, not in-memory worker state. Completed ingest, detected points, cached observations, persisted events, and job status rows are the authority for deciding what still needs to run after a restart.
- **D-03:** The internal orchestration logic should live in normal Python service functions first, with any queue-specific wrapper kept thin. That keeps Phase 6 testable without tying core control flow to a worker framework call site.
- **D-04:** The existing `jobs` row is the canonical lifecycle anchor for Phase 6. The phase may extend it or add adjacent persisted status/detail surfaces, but it should not create a second competing job-truth table.

### API surface and boundaries
- **D-05:** The API remains a thin wrapper over already-existing service seams: ingest, orchestration, event reads, correction writes, and CSV export.
- **D-06:** `POST /ingest` changes from synchronous normalization return to asynchronous job submission. It should still accept the same two source kinds: uploaded local file and approved public URL.
- **D-07:** `GET /jobs/:id` is the primary progress surface for v1. It must expose stage-level status plus partial per-point completion state; SSE may be added later, but polling semantics are non-optional.
- **D-08:** `GET /games/:id/events` returns canonical stored events and supports filters by point, event type, and team. It should not re-run interpretation or compute alternate event truth on the fly.
- **D-09:** `POST /games/:id/corrections` must call the existing immutable correction + memory writer path from Phase 5. Phase 6 adds the public HTTP surface, not a new correction model.
- **D-10:** `GET /exports/:game_id.csv` must export only user-facing canonical event data with stable, versioned columns. Internal trace/cache ids stay out of the CSV.

### Scope and non-goals
- **D-11:** Phase 6 does not add authentication/authorization. Caller identity may remain simple or builder-provided so long as correction provenance still records the acting coach id.
- **D-12:** Phase 6 does not add the alpha web UI. FastAPI route contracts and response shapes should be stable enough that Phase 7 can build on them directly.
- **D-13:** Phase 6 does not reopen earlier schema contracts for `Observation`, `Event`, `MemoryRecord`, or point detection. It orchestrates those artifacts; it does not redesign them.

### the agent's Discretion
- Whether progress detail lives directly on `jobs` or in one adjacent persisted progress structure, so long as the truth is resumable and queryable
- Whether queue integration lands with Dramatiq immediately or behind a thin local orchestrator seam that Dramatiq calls
- The exact API response payload shape, so long as it is explicit, stable, and easy for Phase 7 UI work to consume

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and requirements
- `.planning/ROADMAP.md` — Phase 6 goal, dependencies, and success criteria
- `.planning/REQUIREMENTS.md` — `API-*` and `EXPORT-01` requirements
- `.planning/PROJECT.md` — project modularity, alpha constraints, and operational priorities

### Domain and architecture research
- `.planning/research/SUMMARY.md` — async queue rationale, API surface, and export expectations
- `.planning/research/ARCHITECTURE.md` — package boundaries and API/orchestration role
- `.planning/research/PITFALLS.md` — resume safety, cost duplication, and phase-boundary risks

### Prior phase carry-forward
- `.planning/phases/05-memory-correction-loop/05-04-SUMMARY.md` — completed semantic retrieval and correction-memory substrate
- `.planning/phases/04-interpretation-event-taxonomy/04-03-SUMMARY.md` — canonical event persistence and queryability
- `.planning/phases/03-perception-layer/03-03-SUMMARY.md` — cache-backed observation reuse constraints
- `.planning/phases/02-ingest-point-detection/02-03-SUMMARY.md` — persisted point rows and point-aware downstream ownership

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/sva/api/app.py` already contains the thin FastAPI entrypoint pattern and current `/ingest` request validation surface
- `src/sva/pipeline.py` already expresses the full synchronous control flow that Phase 6 needs to factor into resumable orchestration stages
- `src/sva/ingest/ingest.py` already persists the canonical `jobs` row and normalized ingest result
- `src/sva/points/dao.py`, `src/sva/observations_dao.py`, `src/sva/events_dao.py`, and `src/sva/memory/*` already persist the artifacts a resumed worker can inspect instead of recomputing blindly
- `src/sva/cli.py` already shows the current user-facing invoke/report pattern that Phase 6 should preserve through API parity where possible

### Established Patterns
- The repo prefers narrow DAO/service modules over framework-heavy abstractions
- Persisted pipeline state is kept in Postgres with small ORM row classes plus focused helpers
- Swappable provider boundaries stay isolated; public surfaces should call canonical models and services instead of provider-specific code
- Tests favor focused route/service coverage plus DB-gated migration/DAO smoke tests

### Integration Points
- `src/sva/api/app.py` for FastAPI route growth
- `src/sva/pipeline.py` for stage decomposition into resumable orchestration units
- `src/sva/ingest/ingest.py` and the `jobs` row for lifecycle/progress truth
- `src/sva/events_dao.py` and Phase 5 memory services for read/export/correction API surfaces

</code_context>

<specifics>
## Specific Ideas

- The first execution slice should likely create the job lifecycle and orchestration seam before broadening the HTTP surface.
- Corrections API work should remain thin by delegating directly into the existing immutable correction + memory writer path.
- CSV export should be built from canonical stored events, not from raw observations or LLM output.
- Partial progress should be modeled explicitly enough that killing and restarting work does not create duplicate Gemini calls for already-cached windows.

</specifics>

<deferred>
## Deferred Ideas

- Authenticated coach identity and multi-tenant authorization
- SSE/websocket streaming if polling proves insufficient
- Alpha UI flows, point-boundary editor, and front-end state management
- Eval-gated memory promotion and alpha launch criteria

</deferred>

---
*Phase: 06-async-orchestration-and-api*
*Context gathered: 2026-04-24*
