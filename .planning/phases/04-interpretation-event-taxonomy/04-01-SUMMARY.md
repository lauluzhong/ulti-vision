---
phase: 04-interpretation-event-taxonomy
plan: 01
subsystem: event-contract-rules-validator-backbone
tags: [phase4, interpret, event-schema, rules, validator]

requires:
  - phase: 03-perception-layer / plan 03
    provides: "point-scoped persisted observations and cache-backed perception boundary"
provides:
  - "Widened Event[] interpretation seam"
  - "USAU rules-as-data repo surface"
  - "Deterministic validator backbone for high-value contradictions"
affects: ["04-02", "04-03", "Phase 5", "Phase 7"]

requirements-completed: []

completed: 2026-04-24
status: complete
---

# Phase 04 Plan 01: Event Contract & Rules Backbone Summary

**Established the Phase 4 backbone by widening interpretation to canonical `Event[]`, adding explicit event audit/detail fields, and introducing a repo-visible USAU rulebook plus deterministic validator for the highest-value timeline contradictions.**

## Task Commits

1. `7d10eff` — `feat(04-01): add interpretation contract backbone`

## Accomplishments

### Task 1 — Widened interpret seam and canonical event contract

- Updated the interpreter protocol and runner so interpretation now returns `list[Event]` rather than one synthetic event.
- Extended the canonical `Event` model with:
  - `turnover_subtype`
  - `throw_type`
  - `pass_direction`
  - `prompt_version_hash`
- Kept the event contract model-agnostic and audit-friendly while preserving existing provenance fields (`source_observations`, `rule_refs`, `memory_refs`, `warnings`).
- Updated the Phase 1 Claude stub and interpret tests to conform to the widened seam.

### Task 2 — USAU rules data and deterministic validator backbone

- Added `rulebook/usau_2024_2025.yaml` as a repo-visible USAU alpha rules source.
- Added `src/sva/interpret/rules.py` with:
  - rulebook loading
  - prompt-friendly rules summary
  - deterministic validation for:
    - possession flips without turnover/goal
    - `point_end` without prior `goal`
    - goal/team contradiction against active possession
- Added `tests/test_interpret_rules.py` to lock rules loading and core contradiction detection.

## Verification

- `./.venv/bin/python -m py_compile src/sva/models.py src/sva/interpret/adapters/base.py src/sva/interpret/runner.py src/sva/interpret/adapters/claude.py src/sva/interpret/rules.py tests/test_interpret_adapter.py tests/test_models.py tests/test_interpret_rules.py` → passed
- `./.venv/bin/pytest tests/test_models.py tests/test_interpret_adapter.py tests/test_interpret_rules.py -q` → `13 passed, 1 skipped`

## Deviations / Notes

- The current Claude adapter remains a stub in behavior, but it now conforms to the real `Event[]` seam so the Phase 4 provider work can land without another contract reset.
- Pipeline fan-out has not been updated yet; that remains owned by `04-03`.

## Ready for Next Plan

Phase 4 can now move into `04-02`:

- the interpret seam now matches the architecture
- rules data has a canonical repo surface
- validation can wrap the real adapter instead of being invented ad hoc later

## Self-Check: PASSED

- interpret returns `Event[]`
- rules load from repo data
- deterministic validator exists and is test-locked
- event audit/detail fields are explicit rather than buried in opaque JSON

---
*Phase: 04-interpretation-event-taxonomy*
*Completed: 2026-04-24*
