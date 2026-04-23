---
phase: 03-perception-layer
plan: 02
subsystem: gemini-perceiver-observability
tags: [phase3, gemini, perceiver, observability, retries]

requires:
  - phase: 03-perception-layer / plan 01
    provides: "Observation persistence contract and exact-triple cache key"
provides:
  - "Real Gemini 2.5 Flash perceiver behind the swap-safe Observation seam"
  - "Prompt-hash, latency, retry, and terminal-status perception observability"
  - "Retry-bounded Gemini error handling with explicit exhaustion behavior"
affects: ["03-03", "Phase 4"]

requirements-completed:
  - PERCEIVE-02
  - PERCEIVE-04

completed: 2026-04-23
status: complete
---

# Phase 03 Plan 02: Gemini Adapter & Perception Observability Summary

**Replaced the Phase 1 Gemini stub with a real Gemini 2.5 Flash native-video adapter, while tightening the perception observability contract so prompt hash, latency, retries, and terminal status are visible on both success and failure paths.**

## Task Commits

1. `74d1918` — `feat(03-02): implement Gemini perceiver observability`

## Accomplishments

### Task 1 — Real Gemini adapter with schema-safe Observation output

- Replaced the stubbed `GeminiPerceiver` in `src/sva/perceive/adapters/gemini.py` with a real `google.genai` native-video call path using the swap-safe `Observation` seam.
- Added one canonical perception prompt and a stable `prompt_version_hash` derived from the exact prompt string sent to Gemini.
- Kept provider-specific details inside the adapter by normalizing every response back into canonical `Observation` objects and storing provider escape-hatch identity only via `raw_response_ref`.
- Preserved conservative ambiguity handling by mapping uncertain disc/scene states into the structured fields already added in `03-01`.

### Task 2 — Bounded retry behavior and richer perception observability

- Extended `TraceContext` and `observe_call(...)` in `src/sva/observability/langfuse.py` so perception traces now carry:
  - `prompt_version_hash`
  - `latency_ms`
  - `retry_count`
  - `terminal_status`
- Added capped exponential backoff for retryable Gemini failures and explicit retry-exhaustion behavior rather than silent empty observations.
- Exported `prompt_version_hash(...)` through `src/sva/observability/__init__.py` so later runner/cache work can reuse the exact same hash seam.
- Expanded adapter and observability coverage in:
  - `tests/test_perceive_adapter.py`
  - `tests/test_observability.py`

## Verification

- `./.venv/bin/python -m py_compile src/sva/observability/__init__.py src/sva/observability/langfuse.py src/sva/perceive/adapters/gemini.py tests/test_perceive_adapter.py tests/test_observability.py` → passed
- `./.venv/bin/pytest tests/test_perceive_adapter.py tests/test_observability.py tests/test_models.py -q` → `14 passed, 3 skipped`

## Deviations / Notes

- The installed `google-genai` SDK preserves the real runtime contract cleanly, but its direct `GenerateContentResponse(parsed=...)` constructor drops mocked parsed payloads in tests. The tests now use simpler response doubles so parsing coverage reflects the real adapter seam rather than an SDK constructor quirk.
- Cache-hit short-circuiting remains owned by `run_window(...)` in `03-03`; this plan intentionally stops at the provider and observability seam.

## Ready for Next Plan

Phase 3 can now move into `03-03`:

- the provider boundary is real instead of stubbed
- prompt hashing is stable and reusable as a cache identity
- success and failure observability is explicit before cache-aware reruns are introduced

## Self-Check: PASSED

- Gemini adapter uses the real native-video path
- bounded retry behavior is test-locked
- prompt-hash observability is exported and covered
- failure-path trace updates no longer disappear silently

---
*Phase: 03-perception-layer*
*Completed: 2026-04-23*
