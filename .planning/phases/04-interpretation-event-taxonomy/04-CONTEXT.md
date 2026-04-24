# Phase 4: Interpretation & Event Taxonomy - Context

**Gathered:** 2026-04-24
**Status:** Ready for research and planning
**Source:** GSD auto-resume continuation from completed Phase 3

<domain>
## Phase Boundary

Phase 4 turns the current stubbed `interpret` seam into a real, rules-aware event extraction layer. It consumes point-scoped `Observation` records from Phase 3, composes the canonical rule set into the LLM prompt, validates structured output against the event schema, and persists the full v1 event timeline needed for alpha: possession changes, completions, turnovers, goals, point end, plus best-effort throw type and pass direction with explicit `unknown` fallbacks.

This phase is about the interpretation layer only. It does not add memory retrieval logic beyond the existing stub, async job orchestration, coach-facing corrections UI, or evaluation gating. It may seed the rule-data and deterministic validation seams that later memory and eval phases depend on.

</domain>

<decisions>
## Implementation Decisions

### Core interpretation seam
- **D-01:** Phase 4 upgrades the interpreter boundary from a single `Event` to **`list[Event]` per point**. The roadmap and architecture both define interpretation as producing `Event[]`, and the v1 taxonomy cannot fit truthfully behind a one-event-per-point seam.
- **D-02:** The swap-safe interpreter seam remains the architecture boundary. `make_default_interpreter()` stays the single edit point for provider swaps; downstream pipeline code should consume canonical `Event` objects only.
- **D-03:** Point ownership remains inherited from Phase 2 / Phase 3. Interpret works inside one persisted point’s observations and must not re-decide point boundaries on its own.

### Rule source of truth
- **D-04:** **USAU club/college rules are the canonical v1 rule source**, not WFDF. Research already recommends USAU 2024-2025 club/college rules as the widest alpha fit. Earlier WFDF wording in project docs is treated as stale planning drift, not the authoritative Phase 4 target.
- **D-05:** Rules live as **data, not code**. Phase 4 should introduce a repo-level rule-data surface (for example `rulebook/` or an equivalent dedicated data location) that the interpreter loads at runtime rather than hardcoding rule text inside prompt templates.
- **D-06:** Deterministic rule validation wraps the LLM rather than replacing it. Hard rules should be enforced in code where feasible, but the validator must fail open by annotating or downgrading uncertain cases instead of silently dropping events the validator cannot fully judge.

### Event taxonomy and schema shape
- **D-07:** Phase 4 ships the roadmap’s canonical v1 event rows: `possession_start`, `completion`, `turnover`, `goal`, `point_end`, plus `unknown` as the safety valve. `pull`, foul/travel/pick, and explicit timeout/stoppage events remain out of the v1 closed enum for now.
- **D-08:** Turnover subtype, throw type, and pass direction live as **best-effort structured detail fields** on canonical events, with `"unknown"` as a first-class value wherever evidence is insufficient.
- **D-09:** Pass count per point is treated as a **derived aggregate** from canonical event rows, not a standalone event type. Phase 4 should preserve enough event detail that pass count queries are straightforward later.
- **D-10:** Schema validation is non-optional. LLM outputs that fail the canonical `Event` contract must surface through a dedicated validation path with warnings/traceability; they must never silently disappear.

### Prompting, observability, and memory carry-forward
- **D-11:** Prompt composition should keep three explicit inputs separate: point-scoped observations, rule-data summary, and retrieved memory. During Phase 4, retrieved memory is still allowed to be `[]`, but the prompt builder must preserve that seam for Phase 5.
- **D-12:** Interpret traces should keep the same observability discipline established in Phases 1 and 3: `game_id`, `video_id`, `point_id`, `point_ordinal`, prompt hash, token/cost attribution, and clear failure status.
- **D-13:** Every emitted event must preserve auditability by carrying `source_observations`, `rule_refs`, and `memory_refs`. Empty `memory_refs` are acceptable in Phase 4 because retrieval is still stubbed; missing `source_observations` or `rule_refs` on deterministic calls are not.
- **D-14:** Phase 4 should add an explicit prompt-version identity for interpretation, either as a first-class schema field or an equivalently explicit canonical storage surface. Research already identifies this as necessary for replaying behavior after rules or memory change.

### the agent's Discretion
- The exact on-disk rule-data format (`yaml`, `json`, or split files), as long as it is loader-friendly and human-editable
- Whether deterministic validation lives in one module or a small `interpret.rules` package
- Whether warning annotations are stored in dedicated fields or canonically inside `Event.warnings` plus structured `details`

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and requirements
- `.planning/ROADMAP.md` — Phase 4 goal, dependencies, success criteria, and taxonomy expectations
- `.planning/REQUIREMENTS.md` — `INTERPRET-*` and `EVENT-*` requirements and traceability
- `.planning/PROJECT.md` — project-level modularity, swap-safety, and alpha-scope constraints

### Domain and taxonomy research
- `.planning/research/FEATURES.md` — Ultimate-specific event taxonomy, USAU vs WFDF scope, and v1 event recommendations
- `.planning/research/SUMMARY.md` — VLM→LLM architecture rationale and alpha constraints
- `.planning/research/PITFALLS.md` — prompt-version identity, memory replayability, and rule-contradiction pitfalls
- `.planning/research/ARCHITECTURE.md` — `interpret` package role, `Event[]` output shape, and deterministic validator pattern
- `.planning/research/STACK.md` — Claude Sonnet 4.5 rationale and prompt-caching implications

### Prior phase carry-forward
- `.planning/phases/03-perception-layer/03-03-SUMMARY.md` — Phase 3 completion and cache-backed observation contract
- `.planning/phases/03-perception-layer/03-CONTEXT.md` — point-scoped observation and observability decisions Phase 4 must preserve
- `.planning/phases/02-ingest-point-detection/02-03-SUMMARY.md` — point-aware pipeline ownership assumptions that remain upstream truth

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/sva/interpret/adapters/base.py` already defines the swap-safe `Interpreter` protocol
- `src/sva/interpret/adapters/claude.py` is the current single-file swap point that should grow from stub to real provider adapter
- `src/sva/interpret/runner.py` is the orchestration seam that will likely widen from one `Event` to `list[Event]`
- `src/sva/models.py` already contains canonical `Event` fields for `details`, `source_observations`, `rule_refs`, `memory_refs`, `warnings`, and model metadata
- `src/sva/pipeline.py` already groups observations by persisted point and is the place where a widened `run_point(...)` return shape will fan out into event persistence
- `src/sva/events_dao.py` already persists canonical `Event` rows and is the natural integration seam once interpretation emits multiple events
- `src/sva/memory/retriever.py` already fixes the retrieval interface shape that Phase 4 should preserve even while retrieval still returns `[]`

### Established Patterns
- Stubs are replaced in place rather than wrapped in parallel abstractions; Phases 3 and 4 should mirror one another structurally
- Observability uses `observe_call(...)` and `TraceContext` instead of bespoke logging per adapter
- Repo conventions favor thin service modules plus small deterministic helpers/validators over deep frameworks
- The prior phases consistently preserve one swap-safe seam per major provider boundary

### Integration Points
- interpreter protocol and runner seam in `src/sva/interpret/`
- canonical event model and any schema refinements in `src/sva/models.py`
- deterministic rule-data and validator surface to be introduced for Phase 4
- `src/sva/pipeline.py` where `run_point(...)` output is currently assumed to be one event and will need to fan out safely

</code_context>

<specifics>
## Specific Ideas

- The most important Phase 4 architectural correction is widening `interpret` to `Event[]` without breaking swap-safety.
- Rule-data should be visible and editable in the repo so yearly rule updates stay a data change, not a code archaeology exercise.
- Best-effort classifications like turnover subtype, throw type, and pass direction should degrade to `"unknown"` early rather than encouraging the model to over-claim.
- The deterministic validator should focus first on the highest-value contradictions: impossible team possession flips, goal without offensive possession, point_end without goal, and impossible point ordering.

</specifics>

<deferred>
## Deferred Ideas

- Real memory retrieval and memory-pinned replay behavior beyond preserving the interface and audit trail
- WFDF or UFA-specific rulesets beyond the canonical USAU alpha path
- Foul/travel/pick/stoppage taxonomy expansion
- Evaluation harness enforcement for rule changes or memory promotions

</deferred>

---
*Phase: 04-interpretation-event-taxonomy*
*Context gathered: 2026-04-24*
