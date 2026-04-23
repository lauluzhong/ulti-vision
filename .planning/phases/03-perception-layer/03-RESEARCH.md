# Phase 3: Perception Layer - Research

**Domain:** VLM-backed per-window observation extraction, persisted observation caching, and bounded-rate Gemini perception for Ultimate footage. [VERIFIED: .planning/phases/03-perception-layer/03-CONTEXT.md]
**Date:** 2026-04-23
**Status:** Ready for planning

## What This Phase Must Prove

Phase 3 is the first time the repo stops treating `perceive` as a stub and starts paying real VLM cost. That changes the architectural priority order:

1. **Sampling must stay cost-disciplined** — the roadmap locks 1 fps as default and 3 fps as the v1 ceiling. [VERIFIED: .planning/ROADMAP.md]
2. **Observation output must become a durable intermediate artifact** — persisted between perception and interpretation so prompt iteration and later correction work do not keep re-calling Gemini. [VERIFIED: .planning/research/ARCHITECTURE.md]
3. **Cache hits must be a hard gate before Gemini calls** — this is explicitly called out as a day-one cost control, not an optimization. [VERIFIED: .planning/research/SUMMARY.md] [VERIFIED: .planning/research/PITFALLS.md]
4. **The adapter must handle ambiguity honestly** — amateur Ultimate footage creates disc invisibility, multiple-disc confusion, and temporal conflation risk that the schema needs to express rather than hide. [VERIFIED: .planning/research/PITFALLS.md]

## Research Findings

### 1. Sampling and fps control

- The roadmap requires a **single configurable fps control** with `1` as the default and `3` as the hard v1 ceiling. [VERIFIED: .planning/ROADMAP.md]
- Current `src/sva/ingest/sampler.py` accepts an `fps` argument but does not use it meaningfully yet, which makes it the natural seam for Phase 3 rather than introducing a new sampling module. [VERIFIED: src/sva/ingest/sampler.py]
- Architecture research explicitly recommends starting with **fixed sampling** and only considering adaptive sampling later if evaluation shows recall loss. [VERIFIED: .planning/research/ARCHITECTURE.md]

**Planning implication:** Phase 3 should make fps validation and window idempotency concrete, but should not pull adaptive sampling into scope.

### 2. Observation persistence and cache identity

- The project research is unusually explicit here: observation caching must be keyed on **`(video_id, window_id, prompt_version_hash)`** and must skip the Gemini call entirely on a hit. [VERIFIED: .planning/research/SUMMARY.md] [VERIFIED: .planning/research/PITFALLS.md]
- Architecture guidance says observations should be **persisted rows**, not transient objects, because later phases need to rerun `interpret` from observations without re-paying VLM cost. [VERIFIED: .planning/research/ARCHITECTURE.md]
- The current repo has no `observations` table yet, so this phase needs a new migration + DAO layer rather than an in-memory cache bolted onto `run_window`. [INFERRED from src/sva and migrations]

**Planning implication:** the observation store should be implemented as a first-class persistence layer with:
- canonical Observation payload
- explicit cache key columns
- optional raw-response reference
- fast lookup path before provider invocation

### 3. Gemini adapter direction

- Stack research already selected **Gemini 2.5 Flash** because it is the only cost-feasible frontier model with native video input for this use case. [VERIFIED: .planning/research/STACK.md]
- The architecture and stack docs both assume the VLM adapter remains behind a swap-safe interface, so Phase 3 should deepen the existing `GeminiPerceiver` rather than expanding into multi-provider routing. [VERIFIED: .planning/research/ARCHITECTURE.md] [VERIFIED: src/sva/perceive/runner.py]
- The stub currently already records cost and trace metadata through `observe_call`, which means the real adapter should extend the same shape rather than bypassing it. [VERIFIED: src/sva/perceive/adapters/gemini.py] [VERIFIED: src/sva/observability/langfuse.py]

**Planning implication:** the real adapter should keep:
- `make_default_perceiver()` as the one-file swap point
- `TraceContext` propagation unchanged except for prompt hash enrichment
- cost recording through the existing observability wrapper

### 4. Rate limits, retries, and degraded behavior

- Research explicitly calls out rate limits and VLM spend as the **first production bottleneck**. [VERIFIED: .planning/research/ARCHITECTURE.md]
- The architecture doc specifies **exponential backoff** and a degraded failure path when retries are exhausted. [VERIFIED: .planning/research/ARCHITECTURE.md]
- The roadmap makes per-call cost + latency visibility part of this phase’s acceptance criteria, so retry behavior must remain observable rather than hidden inside a bare SDK loop. [VERIFIED: .planning/ROADMAP.md]

**Planning implication:** retry logic belongs in the adapter or the immediate runner seam, with:
- bounded exponential backoff
- capped retries
- traceable failure state
- no silent fallback to empty observations

### 5. Schema refinements driven by known pitfalls

Two perception failure modes are already documented strongly enough that Phase 3 should reflect them in the schema:

- **Disc invisibility vs absence** — research recommends a more explicit distinction than `visible: bool`. [VERIFIED: .planning/research/PITFALLS.md]
- **Multiple-disc confusion** — research recommends a scene-level flag so downstream interpretation can avoid overconfident event inference. [VERIFIED: .planning/research/PITFALLS.md]

The current `Observation` contract is intentionally minimal and safe, but the pitfall research suggests Phase 3 should extend it in structured ways instead of burying these cases in `free_form_note`.

**Planning implication:** Phase 3 should likely add one or more of:
- `disc.visibility_quality`
- `scene.multiple_discs_possible`
- stronger action-confidence handling

while keeping the model-agnostic contract intact.

## Recommended Plan Shape

The repo is set up cleanly for a **three-plan phase**:

1. **Observation persistence + cache contract**
   - migration for `observations`
   - DAO / lookup helpers
   - cache-first runner path

2. **Real Gemini perception path + schema refinements**
   - native-video adapter implementation
   - prompt hash usage
   - bounded backoff and latency/cost capture
   - refined Observation fields tied to documented pitfalls

3. **Pipeline integration + verification**
   - point-aware window sampling / fps validation
   - pipeline persistence of observations before interpret
   - proof that cache hits skip Gemini entirely
   - DB/integration tests for observation reuse

This sequencing keeps the expensive provider work off the critical path until the cache and persistence contracts exist.

## Anti-Patterns To Avoid

- **Do not implement cache as local JSON or pickle files.** The architecture requires observation reuse across reruns and later phases; this needs first-class persisted state. [VERIFIED: .planning/research/ARCHITECTURE.md]
- **Do not let Gemini calls happen before the cache check.** That defeats the core cost gate for prompt iteration. [VERIFIED: .planning/research/PITFALLS.md]
- **Do not expand Phase 3 into interpretation or memory logic.** This phase should stop at persisted `Observation` output. [VERIFIED: .planning/ROADMAP.md]
- **Do not add adaptive sampling yet.** Fixed 1–3 fps is the locked direction. [VERIFIED: .planning/research/ARCHITECTURE.md]
- **Do not leak provider-specific response structure into canonical tables.** Keep raw provider payloads referenced externally; canonical tables should remain typed and model-agnostic. [VERIFIED: .planning/research/ARCHITECTURE.md]

## Verification Ideas

- Unit tests that `fps > 3` is rejected and `fps in {1,2,3}` flows through one configuration seam.
- DB-gated tests that an observation row round-trips with the cache key triple and canonical payload.
- Runner tests that a cache hit returns persisted observations without invoking the Gemini adapter.
- Adapter tests that bounded retry behavior records cost/trace metadata and fails explicitly after retry exhaustion.
- Pipeline tests that observations are persisted before interpretation runs and can be re-used in a second run without duplicate VLM calls.

## Planner Notes

- Treat the `observations` table and cache lookup path as the phase’s architectural backbone.
- Keep the Phase 2 point-scoped pipeline intact; perception should fill the “observations between windows and interpret” seam rather than reshaping the whole pipeline again.
- Use the existing test split already established by the repo: pure unit tests for contract logic, DB-gated tests for persistence, and one integration test for the stage boundary.

---
*Phase: 03-perception-layer*
*Research prepared: 2026-04-23*
