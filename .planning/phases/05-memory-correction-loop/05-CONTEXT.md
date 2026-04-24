# Phase 5: Memory & Correction Loop - Context

**Gathered:** 2026-04-24
**Status:** Ready for research and planning
**Source:** GSD auto-resume continuation from completed Phase 4

<domain>
## Phase Boundary

Phase 5 turns the current no-op memory seam into a real, model-agnostic memory and correction subsystem. It introduces durable persistence for memory records and immutable coach corrections, implements scoped retrieval for interpretation, and enforces the promotion rules that prevent one coach's conventions from leaking globally during alpha.

This phase is about the **memory package and correction workflow only**. It does not add the public HTTP correction API, the async queue surface, or the eval regression gate UI. Those arrive in later phases. Phase 5 should, however, create the internal services and persisted provenance needed for those later surfaces to remain thin.

</domain>

<decisions>
## Implementation Decisions

### Canonical storage and swap-safety
- **D-01:** For this repo, the canonical persistence path is **Postgres-first**, not the earlier SQLite/LanceDB research sketch. Phase 1-4 already standardized on Postgres, Alembic, and `jobs/events/observations/points`, and Phase 5 must extend that single-store architecture instead of introducing a second primary store.
- **D-02:** `MemoryRecord` remains the canonical model-agnostic memory contract. Phase 5 may add persistence helpers and optional operational metadata, but it must not couple memory rows to a specific LLM, VLM, or prompt format.
- **D-03:** The existing `MemoryRetriever.retrieve(query, tags=None, limit=None)` signature is fixed. Phase 5 may change the body and add collaborators, but not the public signature.
- **D-04:** Embeddings are a separate provider boundary from interpretation. Swapping the embedding model may require a re-embed batch later, but must not require schema changes to `MemoryRecord` or to correction provenance.

### Retrieval semantics
- **D-05:** Retrieval is **tag-filter first, vector-rank second**, with a hard budget of 4-8 records in normal interpret flows. Exact tag filtering narrows the candidate pool before any semantic ranking to reduce noise and cost.
- **D-06:** Retrieval scope for interpretation is `global ∪ coach:<current_coach_id>` when a coach is present, and `global` only when no coach scope is known. Team-scoped memory stays available as a future extension, but is not required for v1.
- **D-07:** If semantic ranking is unavailable for a candidate set, the fail-safe is deterministic tag/filter ordering rather than returning unrelated memories. Phase 5 must not pretend lexical fallback equals semantic retrieval.

### Correction provenance and immutability
- **D-08:** Coach corrections are persisted as **immutable first-class records** in a dedicated corrections table. They are not in-place edits to `events`.
- **D-09:** Every correction must preserve enough provenance to replay the decision later: `coach_id`, `correction_id`, source `event_id`, original event payload snapshot, and the memory refs that were active on the source event.
- **D-10:** The internal correction write path ships in Phase 5, but the public HTTP correction API remains a Phase 6 concern. Phase 5 should expose service/DAO seams that the later API can call directly.

### Promotion and contamination control
- **D-11:** New correction-derived memory records default to `scope="coach:<id>"` and never land in `global` directly.
- **D-12:** Promotion to `scope="global"` hard-blocks unless **at least two distinct `coach_id` values** corroborate the same correction pattern **and** explicit builder curation is present. This is code-enforced, not policy.
- **D-13:** Promotion creates a new promoted memory row or equivalent append-only record; Phase 5 should avoid mutating the semantic content of existing memory records in place.

### Integration with interpretation and auditability
- **D-14:** Interpretation prompts must continue to keep observations, rules, and retrieved memory as separate explicit sections. Phase 5 retrieval should slot into that seam rather than folding memory into hidden adapter state.
- **D-15:** Retrieved memory ids become part of the canonical event audit trail. Once Phase 5 retrieval is live, emitted events should preserve concrete `memory_refs` on persisted rows rather than leaving them empty by default.
- **D-16:** Rulebook data remains authoritative in `rulebook/`. Phase 5 may seed rule memories from that source, but must not create a second conflicting rule truth source.

### the agent's Discretion
- The exact table split between memory rows, promotion evidence, and correction rows, so long as correction provenance and promotion gates remain explicit
- Whether semantic ranking initially uses direct vector SQL or a thin helper module, so long as the retrieval seam remains provider-agnostic
- Whether correction payload snapshots live as canonical JSONB blobs or as thinner normalized fields plus JSONB snapshots

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and requirements
- `.planning/ROADMAP.md` — Phase 5 goal, dependencies, and success criteria
- `.planning/REQUIREMENTS.md` — `MEMORY-*` requirements and traceability
- `.planning/PROJECT.md` — modularity, alpha constraints, and correction-loop intent

### Domain and architecture research
- `.planning/research/SUMMARY.md` — memory-before-alpha rationale, promotion guardrails, and architecture summary
- `.planning/research/ARCHITECTURE.md` — orthogonal memory package, retrieval role, and correction-loop placement
- `.planning/research/PITFALLS.md` — scope collapse, replayability, and memory contamination risks
- `.planning/research/STACK.md` — older memory-store recommendation; treat as partially stale where it conflicts with the implemented Postgres-first repo

### Prior phase carry-forward
- `.planning/phases/04-interpretation-event-taxonomy/04-03-SUMMARY.md` — event persistence and `memory_refs` carry-forward seam
- `.planning/phases/04-interpretation-event-taxonomy/04-CONTEXT.md` — explicit prompt composition and auditability decisions that Phase 5 must preserve
- `.planning/phases/03-perception-layer/03-03-SUMMARY.md` — persisted observations that corrections may later need to reference indirectly through source events

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/sva/memory/retriever.py` already defines the final retrieval signature and a stub implementation
- `src/sva/models.py` already contains canonical `MemoryRecord`, `MemorySource`, and `Event.memory_refs`
- `src/sva/interpret/prompt.py` already renders retrieved memory records as a separate prompt section
- `src/sva/interpret/adapters/claude.py` already accepts retrieved memory as an explicit input and normalizes event-level `memory_refs`
- `src/sva/events_dao.py` already persists canonical `memory_refs` on event rows
- `src/sva/db.py` and the existing Alembic setup already provide the persistence pattern to follow

### Established Patterns
- New persisted pipeline artifacts get their own ORM row class + narrow DAO helpers + migration + DB-gated tests
- Swap-safe provider seams use tiny protocol/service modules rather than framework-heavy orchestration
- Observability and auditability matter more than clever abstraction; canonical row payloads should stay inspectable and replay-friendly
- The repo consistently treats later API surfaces as thin wrappers over already-existing service seams

### Integration Points
- `src/sva/memory/retriever.py` for retrieval behavior
- `src/sva/interpret/prompt.py` and `src/sva/interpret/adapters/claude.py` for using retrieved memory during interpretation
- `src/sva/events_dao.py` and existing event rows for replay/audit provenance
- new Phase 5 persistence seam(s) for memory records and coach corrections

</code_context>

<specifics>
## Specific Ideas

- The first Phase 5 implementation slice should land **canonical persistence** for memory records and corrections before tackling retrieval ranking.
- The correction service should store the original event payload snapshot rather than only an event id, so later replay remains possible even if the event row changes shape.
- Rulebook-derived records should be seedable into memory while keeping `rulebook/` as the authoritative edit surface.
- Promotion checks should be isolated into explicit functions with tests rather than scattered inside retrieval or writer code.

</specifics>

<deferred>
## Deferred Ideas

- Public HTTP correction API and authenticated coach identity flow
- Eval regression gate execution on every promotion (Phase 7)
- UI surfaces for correction review and promotion curation
- Cross-team or organization-scoped memory beyond `global` and `coach:<id>`

</deferred>

---
*Phase: 05-memory-correction-loop*
*Context gathered: 2026-04-24*
