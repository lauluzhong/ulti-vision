---
phase: 04-interpretation-event-taxonomy
plan: 02
subsystem: claude-interpreter-prompt-observability
tags: [phase4, interpret, claude, prompt, observability]

requires:
  - phase: 04-interpretation-event-taxonomy / plan 01
    provides: "Event[] seam, USAU rules data, and validator backbone"
provides:
  - "Real Claude interpretation adapter"
  - "Prompt-builder seam for observations + rules + memory"
  - "Interpret prompt-hash and failure-path observability"
affects: ["04-03", "Phase 5", "Phase 7"]

requirements-completed: []

completed: 2026-04-24
status: complete
---

# Phase 04 Plan 02: Claude Adapter & Prompt Composition Summary

**Replaced the Phase 1 interpretation stub with a real Claude SDK path, factored prompt construction into its own seam, and preserved interpret observability so prompt-version identity and validation failures remain visible instead of disappearing inside the adapter.**

## Task Commits

1. `8f7ef70` — `feat(04-02): implement Claude interpretation adapter`

## Accomplishments

### Task 1 — Real Claude interpretation path and prompt builder

- Reworked `src/sva/interpret/adapters/claude.py` to use the Anthropic SDK `messages.create(...)` path with structured JSON-schema output.
- Added `src/sva/interpret/prompt.py` so prompt construction now explicitly composes:
  - point-scoped observations
  - USAU rules summary
  - retrieved memory records
- Normalized canonical event defaults so:
  - completion rows degrade `throw_type` / `pass_direction` to `"unknown"` when missing
  - turnover rows degrade `turnover_subtype` to `"unknown"` when missing
- Expanded `tests/test_interpret_adapter.py` to cover multi-event parsing and invalid structured output.

### Task 2 — Interpret observability and failure surfaces

- Reused the existing `observe_call(...)` / `TraceContext` seam rather than inventing interpret-specific logging.
- Added prompt-version hashing for interpretation based on the actual composed prompt.
- Surfaced validation/failure state through `updated_ctx` so Langfuse traces can record `terminal_status` rather than losing the error path.
- Extended `tests/test_observability.py` with an interpret-specific prompt-hash success-path assertion.

## Verification

- `./.venv/bin/python -m py_compile src/sva/interpret/adapters/claude.py src/sva/interpret/prompt.py tests/test_interpret_adapter.py tests/test_observability.py` → passed
- `./.venv/bin/pytest tests/test_interpret_adapter.py tests/test_observability.py -q` → `9 passed, 3 skipped`

## Deviations / Notes

- The adapter now emits real canonical `Event[]`, but the pipeline fan-out still needs the `04-03` integration step so runtime and persistence fully align with the widened seam.
- Validation currently surfaces through explicit parse/failure status; deeper deterministic rule enforcement remains anchored in the Phase 4 rules backbone from `04-01`.

## Ready for Next Plan

Phase 4 can now move into `04-03`:

- the provider boundary is real instead of stubbed
- interpret prompt composition is isolated from the adapter body
- prompt-version identity is explicit before multi-event pipeline persistence lands

## Self-Check: PASSED

- Claude SDK path is real
- prompt builder is explicit
- canonical multi-event parsing is test-locked
- interpret observability preserves prompt hash and failure surfaces

---
*Phase: 04-interpretation-event-taxonomy*
*Completed: 2026-04-24*
