---
phase: 07-evaluation-harness-and-alpha-ui
status: planned
created: 2026-04-25
updated: 2026-04-25
---

# Phase 07 Context

## Goal

Ship the evaluation harness and minimal coach-facing alpha UI needed to open alpha honestly, while keeping the missing real gold set and independent annotator dependency explicit instead of papering it over.

## Locked Decisions

1. **Phase 7 is split into five plans across eval, point-boundary backend, and UI.**
   - `07-01` eval contracts, gold-set loader, and metrics harness
   - `07-02` memory-promotion regression gate
   - `07-03` point-boundary API and rebucketing service
   - `07-04` minimal SvelteKit alpha UI scaffold
   - `07-05` correction UI and point-boundary editor

2. **Real gold labels are an honest external blocker.**
   - The repo can ship the harness, readiness checks, and blocked-state reporting.
   - The repo cannot honestly claim alpha readiness until at least 3 full games / ~40 points are labeled by the builder plus an independent annotator, with agreement recorded.

3. **Eval harness stays pure-Python and deterministic first.**
   - Matching, metrics, and gate logic live under `src/sva/eval/`.
   - Expensive VLM/LLM replay is integration scope; fast unit coverage owns the scoring and gate semantics.

4. **Global memory promotion must be gated by eval in code, not policy.**
   - Phase 5 distinct-coach + builder-curation gates remain.
   - Phase 7 adds a hard regression block if any event-type recall drops by >= 3 points or if no eligible gold set is available.

5. **UI stack follows the project research recommendation: SvelteKit 2.**
   - Create a fresh `apps/web/` app because no frontend workspace exists yet.
   - The alpha UI targets four flows: submit game, poll status, review event timeline, and edit corrections/boundaries.

6. **Point-boundary editing is not UI-only.**
   - Phase 7 must add backend point list/update APIs plus rebucketing of downstream events.
   - The plan must not pretend a client-only editor satisfies `POINT-02`.

7. **Phase 7 keeps progress transport simple.**
   - Use polling over the current job API first.
   - Do not silently promise SSE/WebSocket progress until a real backend stream exists.

8. **Stats stay v1-sized.**
   - Surface completion %, turnover count, goals, throw-type mix, and pass count.
   - Avoid v2 line-detection or roster-driven metrics.

## Known Gaps Entering Phase 7

- No frontend workspace exists.
- No video-serving endpoint exists for timeline scrubbing.
- No point list/update/rebucket API exists.
- No real gold-set fixtures or independent annotator metadata exist in the repo.
- `uv.lock` is user-dirty and must remain untouched unless the user explicitly wants it updated.
