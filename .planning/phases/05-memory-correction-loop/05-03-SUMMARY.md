---
phase: 05-memory-correction-loop
plan: 03
subsystem: correction-writer-and-promotion-gate
tags: [phase5, memory, corrections, promotion, contamination-control]

requires:
  - phase: 05-memory-correction-loop / plan 01
    provides: "immutable corrections and persisted memory substrate"
  - phase: 05-memory-correction-loop / plan 02
    provides: "scoped retrieval seam and memory-aware interpret audit trail"
provides:
  - "Correction-to-memory derivation in coach scope"
  - "Code-enforced global promotion gate"
  - "Explicit tests that one coach cannot poison global memory"
affects: ["05-04", "Phase 6", "Phase 7"]

requirements-completed:
  - MEMORY-03
  - MEMORY-04

completed: 2026-04-24
status: complete
---

# Phase 05 Plan 03: Correction Writer & Promotion Gate Summary

**Turned the correction loop into a real internal write path by deriving coach-scoped memory rows from immutable corrections and hard-blocking global promotion unless the distinct-coach and builder-curation rules both pass.**

## Task Commits

1. `85f6b5e` — `feat(05-03): add correction writer and promotion gate`

## Accomplishments

### Task 1 — Coach-scoped correction-to-memory derivation

- Added [src/sva/memory/writer.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/memory/writer.py) with:
  - `correction_to_memory_records(...)`
  - deterministic tag derivation from correction context
  - replay-friendly `embedding_input` construction
- Defaulted all correction-derived memory rows to `scope="coach:<id>"`.
- Updated [src/sva/memory/__init__.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/memory/__init__.py) to export the new writer helpers.

### Task 2 — Multi-coach promotion gate

- Added `can_promote_global(...)` and `promote_memory_record(...)` in [src/sva/memory/writer.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/memory/writer.py).
- Enforced both conditions in code:
  - at least two distinct `coach_id` values
  - explicit builder curation
- Added [tests/test_memory_writer.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/tests/test_memory_writer.py) to prove:
  - corrections derive coach-scoped memory rows by default
  - promotion requires distinct coaches plus builder curation
  - single-coach loops raise instead of silently promoting

## Verification

- `./.venv/bin/python -m py_compile src/sva/memory/writer.py src/sva/memory/__init__.py tests/test_memory_writer.py tests/test_memory_retriever.py` → passed
- `./.venv/bin/pytest tests/test_memory_writer.py tests/test_memory_retriever.py -q` → `7 passed`

## Deviations / Notes

- The promotion gate is now code-enforced, but the later eval-regression gate on promotion remains a Phase 7 concern.
- Phase 5 still needs `05-04` before it can claim full `MEMORY-02` coverage, because current retrieval is tag-first with deterministic fallback rather than real semantic ranking.

## Ready for Next Plan

Phase 5 now has one remaining gap:

- `05-04` semantic-ranking closure for model-agnostic memory retrieval

## Self-Check: PASSED

- corrections now generate coach-scoped memory rows
- global promotion cannot happen from a single-coach loop
- builder review is a hard gate, not policy-only
- append-only promotion behavior is explicit in code

---
*Phase: 05-memory-correction-loop*
*Completed: 2026-04-24*
