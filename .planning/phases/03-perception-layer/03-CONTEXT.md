# Phase 3: Perception Layer - Context

**Gathered:** 2026-04-23
**Status:** Ready for planning
**Source:** GSD auto-discuss continuation from completed Phase 2

<domain>
## Phase Boundary

Phase 3 turns the current stubbed `perceive` seam into a real, cost-disciplined VLM layer. It samples per-point windows at a configurable fps, sends those windows through a Gemini-first adapter that emits structured `Observation` records, persists those observations as first-class rows, and short-circuits repeat work through `(video_id, window_id, prompt_version_hash)` cache hits so prompt iteration does not re-pay Gemini cost.

This phase is about the VLM layer only. It does not expand the event taxonomy, memory logic, async orchestration, or coach-facing UI.

</domain>

<decisions>
## Implementation Decisions

### Sampling and window contracts
- **D-01:** Phase 3 keeps the existing `PerceiveWindow` / `Observation` boundary and extends the current sampler rather than replacing it. Point-aware orchestration from Phase 2 remains the upstream owner of which windows belong to which point; Phase 3 only makes those windows configurable and VLM-backed.
- **D-02:** The default sampling rate stays **1 fps**, and **3 fps is a hard v1 ceiling**. Requests above 3 fps fail fast with a clear validation error instead of silently running at higher cost.
- **D-03:** Sampling configuration should remain a single-edit control surface that later CLI/API layers can pass through unchanged. The repo should not grow separate fps knobs for sampler, perceiver, and pipeline internals.

### Observation schema and perception output
- **D-04:** `Observation` stays the single canonical perception contract and remains model-agnostic. Gemini-specific raw payloads may be referenced externally, but canonical downstream tables consume only typed `Observation` data.
- **D-05:** Phase 3 may evolve the `Observation` schema where the research already identified perception blind spots, especially around disc ambiguity and off-field confusion. The most likely additions are explicit disc-visibility quality and a scene-level “multiple discs possible” flag rather than free-form prompt prose.
- **D-06:** Confidence should stay structured and conservative. When the model cannot infer a field fact cleanly, the schema should preserve uncertainty instead of forcing a confident-but-wrong observation.

### Caching and persistence
- **D-07:** Observation caching is a first-class storage contract in this phase, not an in-memory optimization. Cached outputs must survive process restarts and support rerunning downstream interpretation without re-calling Gemini.
- **D-08:** Cache identity is the exact triple from the roadmap and research: `(video_id, window_id, prompt_version_hash)`. A hit on that triple must skip the Gemini call entirely and return persisted observations.
- **D-09:** Cached observations should live in Postgres alongside the rest of the pipeline state, with one first-class persistence path rather than ad hoc JSON files or ephemeral local caches. Raw provider responses can remain referenced out-of-band by `raw_response_ref`.

### Gemini adapter behavior
- **D-10:** Gemini 2.5 Flash remains the default perceiver in Phase 3 because the stack research already selected native video input as the cost-feasible path. Phase 3 should deepen that adapter, not introduce multi-provider branching yet.
- **D-11:** The adapter should use Gemini’s native video path and preserve the existing single-edit swap point (`make_default_perceiver`). No downstream code should know whether the active perceiver is Gemini or a future provider.
- **D-12:** Rate-limit handling is mandatory in this phase: bounded exponential backoff with a cap, structured logging/trace metadata, and explicit degraded failure behavior after retries are exhausted. Phase 3 should not silently swallow exhausted VLM failures.

### Integration with prior phases
- **D-13:** Phase 2’s persisted point rows remain the source of truth. Perception work runs inside those point buckets rather than reconstructing point membership on its own.
- **D-14:** Langfuse trace continuity is preserved. Every perception call should continue to carry `game_id`, `video_id`, `window_id`, `point_id`, and `prompt_version_hash`, with cost and latency visible at the window level.
- **D-15:** Phase 3 must preserve the current pipeline shape where observations are persisted before interpretation. Re-running interpret against cached observations is a core design outcome, not a future optimization.

### the agent's Discretion
- Exact observation-table column layout, as long as it preserves the cache key, canonical Observation payload, and raw-response linkage
- The precise retry schedule and cap values for Gemini backoff
- Whether schema refinements land all at once or in a smaller sequence across multiple Phase 3 plans

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and acceptance criteria
- `.planning/ROADMAP.md` — Phase 3 goal, dependencies, success criteria, and the locked 1 fps / 3 fps envelope
- `.planning/REQUIREMENTS.md` — PERCEIVE-01, PERCEIVE-02, PERCEIVE-03, PERCEIVE-04 definitions and traceability
- `.planning/PROJECT.md` — modularity, cost discipline, and per-point decomposition as project-level constraints

### Prior phase carry-forward
- `.planning/phases/02-ingest-point-detection/02-CONTEXT.md` — point-assignment and point-source-of-truth decisions that Phase 3 inherits
- `.planning/phases/02-ingest-point-detection/02-03-SUMMARY.md` — current point-aware pipeline seam and event propagation behavior
- `.planning/phases/01-foundation-narrow-vertical-slice/01-CONTEXT.md` — swap-safe adapter, Postgres, Langfuse, and settings decisions that Phase 3 must preserve

### Research and architecture
- `.planning/research/SUMMARY.md` — perception-layer stack choice, cache requirement, and cost/risk framing
- `.planning/research/ARCHITECTURE.md` — `perceive` package role, idempotent window caching, and persist-before-interpret architecture
- `.planning/research/PITFALLS.md` — temporal confusion, disc ambiguity, and cache/rate-limit pitfalls to actively design around
- `.planning/research/STACK.md` — Gemini 2.5 Flash rationale, pricing, and rate-limit envelope

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/sva/perceive/adapters/base.py` already defines the swap-safe `Perceiver` protocol and `PerceiveWindow`
- `src/sva/perceive/adapters/gemini.py` is the current single-file swap point that should grow from stub to real adapter
- `src/sva/perceive/runner.py` is the existing orchestration seam for cache checks and adapter invocation
- `src/sva/observability/langfuse.py` and `src/sva/observability/cost.py` already provide trace metadata and cost attribution primitives that Phase 3 should extend rather than replace
- `src/sva/pipeline.py` now runs point-aware orchestration and is the place where persisted observations will feed the later interpret stage

### Established Patterns
- Contracts are versioned Pydantic models first; adapters and persistence conform to those contracts instead of leaking provider response shapes
- Phase work prefers thin service modules + small DAO layers + migrations instead of scattered raw SQL
- Point membership is already persisted and propagated through `TraceContext`, so perception should attach to that existing context rather than inventing parallel identifiers

### Integration Points
- sampler extension around `src/sva/ingest/sampler.py`
- perception persistence layer adjacent to the current pipeline and DAO structure
- Gemini adapter implementation in `src/sva/perceive/adapters/gemini.py`
- cache lookup path in the perceive runner / pipeline boundary before any Gemini call is made

</code_context>

<specifics>
## Specific Ideas

- The cache gate should be observable, not implicit: it should be possible to prove “zero duplicate Gemini calls for the same `(video_id, window_id, prompt_version_hash)`” from tests and traces.
- Schema refinements should target the perception failure modes already documented in research, especially disc visibility ambiguity and multiple-disc confusion.
- Native Gemini video input remains the preferred path; client-side frame extraction should only appear if the official API path forces it.

</specifics>

<deferred>
## Deferred Ideas

- Multi-provider perception routing beyond the existing single-edit swap point
- Adaptive sampling beyond the fixed 1–3 fps envelope
- Hard-clip escalation to Gemini 2.5 Pro
- UI or manual cache-inspection tools

</deferred>

---
*Phase: 03-perception-layer*
*Context gathered: 2026-04-23*
