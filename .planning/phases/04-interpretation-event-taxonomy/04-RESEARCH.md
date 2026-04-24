# Phase 4: Interpretation & Event Taxonomy - Research

**Domain:** Rules-aware point-level event extraction for Ultimate Frisbee using point-scoped `Observation` records, a Claude-first LLM adapter, and deterministic validation around a canonical event schema. [VERIFIED: .planning/phases/04-interpretation-event-taxonomy/04-CONTEXT.md]
**Date:** 2026-04-24
**Status:** Ready for planning

## What This Phase Must Prove

Phase 4 is where the repo stops treating interpretation as a placeholder and starts producing the product’s real surface area: the event timeline coaches care about. That changes the architectural priority order:

1. **The interpret seam must widen to `Event[]`** because one point can contain multiple completions, turnovers, and a goal. [VERIFIED: .planning/research/ARCHITECTURE.md]
2. **Rules must be data-backed and replayable** so yearly rule updates are file changes and interpretation can be audited later. [VERIFIED: .planning/research/ARCHITECTURE.md] [VERIFIED: .planning/research/PITFALLS.md]
3. **The model must degrade honestly to `unknown`** for direction, throw type, and ambiguous turnover subtype instead of over-claiming. [VERIFIED: .planning/research/FEATURES.md] [VERIFIED: .planning/ROADMAP.md]
4. **Validation cannot be “prompt only.”** Research explicitly recommends a deterministic validator around the LLM output for state-change contradictions. [VERIFIED: .planning/research/ARCHITECTURE.md]

## Research Findings

### 1. The current interpret seam is narrower than the intended architecture

- The current `Interpreter` protocol and `run_point(...)` runner return a single `Event`, and the Phase 1 Claude adapter emits one placeholder `unknown` event. [VERIFIED: src/sva/interpret/adapters/base.py] [VERIFIED: src/sva/interpret/runner.py] [VERIFIED: src/sva/interpret/adapters/claude.py]
- The architecture doc is explicit that `interpret` should reconcile one point’s observations into canonical **`Event[]`** and persist those multiple rows into the events store. [VERIFIED: .planning/research/ARCHITECTURE.md]
- The roadmap success criteria for Phase 4 require multiple event types on the same point timeline, which is impossible to represent truthfully through a single-event boundary. [VERIFIED: .planning/ROADMAP.md]

**Planning implication:** widening the interpreter contract to `list[Event]` is not optional cleanup; it is the first architectural task in the phase.

### 2. USAU is the right alpha rule source, despite stale WFDF wording

- The phase title in `ROADMAP.md` says “USAU-rule composition,” but one success criterion still mentions the WFDF rulebook. This is inconsistent. [VERIFIED: .planning/ROADMAP.md]
- The domain research resolves the ambiguity: build against **USAU 2024-2025 club/college rules** for alpha, and treat WFDF variations as later expansion. [VERIFIED: .planning/research/FEATURES.md]
- Research also recommends that the app note the rules basis explicitly so coaches understand what standard is being applied. [VERIFIED: .planning/research/FEATURES.md]

**Planning implication:** Phase 4 should lock USAU as the canonical rule-data source and preserve a future-compatible data path for additional rulesets later.

### 3. Event taxonomy should stay narrow and coach-legible

- The research-backed v1 event set is intentionally simpler than the full rulebook. The highest-value, most-detectable rows are `possession_start`, `completion`, `turnover`, `goal`, `point_end`, and `unknown`. [VERIFIED: .planning/research/FEATURES.md]
- `pull` is useful for point-boundary anchoring but is not required by the v1 requirements or roadmap success criteria. [VERIFIED: .planning/REQUIREMENTS.md] [VERIFIED: .planning/research/FEATURES.md]
- Foul/travel/pick/stoppage events are explicitly deferred due to poor visual reliability and low alpha value. [VERIFIED: .planning/research/FEATURES.md]
- Turnover subtype, throw type, and pass direction are best-effort classifications and should degrade to `"unknown"` when evidence is weak. [VERIFIED: .planning/research/FEATURES.md] [VERIFIED: .planning/ROADMAP.md]

**Planning implication:** Phase 4 should keep the closed enum narrow and put finer-grained classification into structured event details with explicit unknown fallbacks.

### 4. Deterministic validation is the main guardrail against “LLM sounds plausible”

- The architecture doc recommends a deterministic validator around interpretation to catch contradictions like possession flips without a turnover or goal events that do not align with team possession. [VERIFIED: .planning/research/ARCHITECTURE.md]
- The validator is not expected to cover every rule edge case; it should reject or annotate only the highest-value contradictions and fail open for the rest. [VERIFIED: .planning/research/ARCHITECTURE.md]
- Research explicitly warns against “let the LLM handle rules” as a primary design. [VERIFIED: .planning/research/PITFALLS.md]

**Planning implication:** early Phase 4 should introduce a small deterministic validator focused on timeline/state consistency, not attempt exhaustive codification of the entire rulebook in one pass.

### 5. Auditability requirements already exist in the schema, but one piece is still missing

- `Event` already contains `source_observations`, `rule_refs`, `memory_refs`, `warnings`, and model metadata, which gives Phase 4 a strong audit trail foundation. [VERIFIED: src/sva/models.py]
- Research warns that interpretation becomes impossible to replay correctly if the exact rules/memory/prompt context are not pinned per event. [VERIFIED: .planning/research/PITFALLS.md]
- The pitfall guidance specifically calls out storing a prompt-version identity on every event row. [VERIFIED: .planning/research/PITFALLS.md]

**Planning implication:** Phase 4 should add an explicit interpretation prompt-version identity somewhere canonical, preferably on `Event` itself or a first-class persisted equivalent rather than burying it inside opaque JSON.

### 6. Memory stays stubbed, but the seam must remain real

- `MemoryRetriever.retrieve(...)` already has the final interface shape and intentionally returns `[]` until Phase 5. [VERIFIED: src/sva/memory/retriever.py]
- Architecture guidance says interpretation should accept rules + retrieval results together, with a rules-only prompt as the fallback when retrieval is empty. [VERIFIED: .planning/research/ARCHITECTURE.md]

**Planning implication:** Phase 4 should build the prompt composition seam as if memory were active, but not implement real retrieval or memory writes yet.

### 7. Claude Sonnet 4.5 is still the right default interpreter

- Stack research chose Claude Sonnet 4.5 for rule-based reconciliation because of instruction-following quality, structured-output reliability, and prompt caching economics on large repeated prefixes like rules/examples. [VERIFIED: .planning/research/STACK.md]
- The current repo already has a swap-safe `ClaudeInterpreter`, so Phase 4 should deepen that one file rather than introducing model routing. [VERIFIED: src/sva/interpret/adapters/claude.py]

**Planning implication:** the real provider work belongs inside `src/sva/interpret/adapters/claude.py` with observability through the existing `observe_call(...)` wrapper.

## Recommended Plan Shape

Phase 4 is cleanest as a **three-plan phase**:

1. **Event contract + rules data + deterministic validator backbone**
   - widen `Interpreter` / `run_point(...)` to `list[Event]`
   - refine `Event` schema for auditability and best-effort detail fields
   - introduce repo-level USAU rule-data files and a minimal deterministic validator

2. **Real Claude interpretation path**
   - replace the stubbed Claude adapter with a real structured-output path
   - compose observations + rules + retrieved memory into one prompt builder
   - record prompt hash, rule refs, memory refs, and validation failure surfaces

3. **Pipeline fan-out + event persistence verification**
   - update pipeline to persist multiple events per point
   - preserve point ownership and point-scoped queries
   - add integration tests proving multi-event fan-out and schema/validator behavior

This ordering mirrors the repo’s established pattern: contract/backbone first, provider integration second, pipeline integration third.

## Anti-Patterns To Avoid

- **Do not keep the single-event interpreter seam.** That would force synthetic compression and make Phase 4 incapable of representing real point timelines.
- **Do not hardcode rules inside prompt strings only.** The rule-data source must live in a dedicated, inspectable file surface. [VERIFIED: .planning/research/ARCHITECTURE.md]
- **Do not make throw type, pass direction, or turnover subtype required/confident by default.** These are explicitly best-effort with `unknown` fallbacks. [VERIFIED: .planning/research/FEATURES.md]
- **Do not implement real memory behavior in this phase.** Preserve the retrieval seam, but keep retrieval itself stubbed. [VERIFIED: src/sva/memory/retriever.py]
- **Do not silently drop invalid LLM output.** Validation failures must surface via warnings, traces, and explicit fallback behavior. [VERIFIED: .planning/REQUIREMENTS.md]

## Verification Ideas

- Unit tests proving `run_point(...)` now returns canonical `Event[]` and accepts a custom interpreter without downstream changes.
- Rule-data loader tests proving USAU rules are loaded from data files, not code constants.
- Deterministic validator tests for core contradictions:
  - impossible team possession flip without turnover
  - goal event with conflicting team/state
  - point_end emitted without a goal/terminal event
- Adapter tests proving Claude structured output parses into multiple canonical events and degrades to `unknown` safely.
- Pipeline tests proving one point can persist multiple event rows and remain queryable by `point_id`, `event_type`, and team.

## Planner Notes

- Treat widening the interpreter seam to `Event[]` as the enabling architectural step for the whole phase.
- Favor a minimal, high-signal validator in v1 over ambitious full-rule codification.
- Keep the event taxonomy coach-legible and alpha-focused; avoid prematurely adding every possible Ultimate-specific call.
- Preserve the memory and observability seams even where Phase 4 still uses empty retrieval and bounded fallback behavior.

---
*Phase: 04-interpretation-event-taxonomy*
*Research prepared: 2026-04-24*
