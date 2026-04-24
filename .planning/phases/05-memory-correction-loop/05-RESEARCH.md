# Phase 5: Memory & Correction Loop - Research

**Generated:** 2026-04-24
**Status:** Planning memo for implementation

## Summary

The repo is ready for Phase 5 because the memory seam already exists at every important boundary but still behaves as an intentional stub. `MemoryRetriever.retrieve(...)` is fixed and async, `MemoryRecord` is already model-agnostic in `src/sva/models.py`, interpretation already accepts retrieved memory explicitly in `src/sva/interpret/prompt.py`, and canonical events already persist `memory_refs` in `src/sva/events_dao.py`. That means Phase 5 does not need to invent a new abstraction layer; it needs to fill in the real persistence, retrieval, and correction-writing behavior behind seams the earlier phases deliberately left open.

The main planning drift to resolve is storage strategy. Early stack research suggested SQLite + JSONL + LanceDB, but the implemented repo now has a clear Postgres/Alembic center of gravity: Phase 1-4 already persist jobs, events, points, and observations in Postgres, and the architecture summary explicitly says the full state lives in one Postgres instance with pgvector. Introducing a second primary memory store now would increase operational and migration complexity for no offsetting benefit. Phase 5 should therefore extend the existing Postgres-first design, keep `embedding_ref` and `embedding_input` on the canonical memory model, and make embedding-provider swaps a data refresh concern rather than a storage-architecture fork.

Coach-correction contamination is the highest-risk domain issue in this phase. The research record is consistent here: one coach's conventions must not become global memory just because they are the first or most active user. That means the promotion gate is not polish; it is the core correctness mechanism for the whole memory loop. Corrections must default into `coach:<id>` scope, promotion to `global` must require at least two distinct coaches plus explicit builder curation, and the repo must preserve enough provenance to replay how a bad decision was made. In practice that means immutable correction rows, append-only or promotion-safe memory semantics, and explicit `memory_refs` propagation through the interpret path.

## Verified Repo Facts

- `MemoryRetriever.retrieve(...)` is currently a no-op stub in `src/sva/memory/retriever.py`, but its signature already includes `current_coach_id`, `budget`, optional `tags`, and `limit`.
- `MemoryRecord` and `MemorySource` are already defined in `src/sva/models.py` with the key model-agnostic fields Phase 5 needs: `kind`, `tags`, `scope`, `source`, `embedding_ref`, `embedding_input`, `payload`, `confidence`, `corroborations`, `created_at`, and `last_used_at`.
- Interpretation already keeps memory explicit:
  - `src/sva/interpret/prompt.py` renders `Retrieved memory records` as its own prompt section
  - `src/sva/interpret/adapters/claude.py` receives `retrieved: list[MemoryRecord]`
- Event persistence already supports the audit trail Phase 5 needs because `Event.memory_refs` exists in the schema and `src/sva/events_dao.py` persists it.
- The current Python environment does **not** have the `pgvector` Python package installed, even though the Postgres extension is created in earlier migrations. This means the first execution slice should not depend on ORM-level `pgvector` bindings being present.

## Planning Conclusions

### 1. Phase 5 should begin with persistence, not ranking

The safest and most repo-consistent first slice is to land:
- a `memory_records` table
- a `corrections` table
- narrow DAOs/services for writing and reading canonical rows
- DB-gated tests and migration coverage

This creates the durable substrate for later retrieval and promotion logic without forcing the team to solve vector ranking and correction promotion in the same change.

### 2. Retrieval should preserve the fixed seam and fail safely

The roadmap requires tag-filter-first + vector-rank-second retrieval, but the repo also needs to remain honest when semantic ranking is unavailable. The correct fail-safe is:
- exact scope + tag filtering first
- bounded candidate count
- semantic ranking when embeddings are present
- deterministic fallback ordering when embeddings are not present

What Phase 5 must not do is silently return unrelated memories just to satisfy the budget.

### 3. Corrections are internal write-path first, API second

The Phase 6 roadmap owns `POST /games/:id/corrections`, so Phase 5 should not burn scope on a public HTTP surface. Instead, it should provide internal service functions that:
- accept a canonical correction payload
- persist an immutable correction record with provenance
- derive one or more candidate memory rows in coach scope
- expose promotion checks as explicit functions that later API/UI surfaces can call

This keeps the API phase thin and lowers the risk that Phase 5 accidentally sprawls into frontend/backend integration work.

## Recommended Plan Split

### 05-01 — Memory persistence and correction ledger

Create the Postgres/Alembic foundation for `memory_records` and `corrections`, plus canonical DAO/service helpers and tests. This plan should also add any canonical correction model(s) needed in `src/sva/models.py`.

### 05-02 — Scoped retrieval and interpret integration

Replace the stub retriever body with real scope-aware lookup and retrieval ordering. Update interpretation so retrieved memory ids are preserved on emitted events even if the LLM omits them. Keep the retrieval API shape unchanged.

### 05-03 — Correction writer and promotion gate

Implement the correction-to-memory writer path, coach-scope defaults, and the multi-coach + builder-review promotion guard. Add focused tests that prove a single coach cannot reach `global` scope.

## Risks to Watch

- **Store drift:** do not reintroduce a second primary memory store after four phases of Postgres-first work.
- **Replay gaps:** if correction rows do not snapshot original event payloads and active memory ids, the future eval/debug loop will be weak.
- **False semantic confidence:** without embeddings in place, retrieval should degrade to deterministic filtering rather than claiming semantic ranking exists.
- **Hidden promotion logic:** if corroboration rules live in ad hoc call sites instead of a dedicated gate function, Phase 6/7 will be hard to trust.

## Immediate Recommendation

Plan and then execute `05-01` first:
- canonical persistence for memory/corrections
- migration coverage
- narrow DAOs/services
- no public API yet

That gives the phase a truthful, testable foothold before retrieval and promotion complexity lands.

---
*Phase: 05-memory-correction-loop*
*Research generated: 2026-04-24*
