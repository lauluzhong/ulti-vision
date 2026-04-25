---
phase: 07-evaluation-harness-and-alpha-ui
type: research
created: 2026-04-25
updated: 2026-04-25
---

# Phase 07 Research

## Summary

Phase 7 has two parallel tracks:

- **Eval track:** buildable now with deterministic metrics, gates, and harness plumbing.
- **UI track:** buildable as a minimal SvelteKit alpha shell, but blocked from full completion by missing point-boundary backend APIs, video serving, and real gold data.

## Eval Findings

- Critical failure modes:
  - missed core events
  - confident unsupported ambiguity fields
  - wrong `point_id` / wrong in-point timestamps
  - memory promotion regressions
  - non-reproducible eval runs
- Required reporting:
  - per-event-type precision and recall only; no macro-average headline without breakdown
  - alpha gate:
    - completion recall >= 85%
    - completion precision >= 70%
    - goal recall >= 95%
    - possession-change recall >= 95%
- Gold-set contract:
  - at least 3 full games / ~40 points
  - builder + independent annotator labels
  - point-aware labels with timestamp tolerances
- Honest blocked state:
  - if real gold data or annotator metadata is missing, the harness reports `gold_set_ready=false` / blocked rather than pass/fail

## UI Findings

- Recommended stack: **SvelteKit 2** in a fresh `apps/web/` workspace.
- Core alpha screens:
  - submit game
  - processing status
  - game review
  - point-boundary editor
- Existing backend routes already useful to the UI:
  - `POST /ingest`
  - `GET /jobs/{job_id}`
  - `GET /games/{game_id}/events`
  - `POST /games/{game_id}/corrections`
  - `GET /exports/{game_id}.csv`
- Backend gaps the UI cannot fake:
  - video access route for scrubbing
  - point list/update APIs
  - rebucketing after boundary edits

## Implementation Guidance

- Build Phase 7 in this dependency order:
  - `07-01` eval contracts/metrics
  - `07-03` point-boundary API/rebucketing
  - `07-02` promotion regression gate
  - `07-04` SvelteKit scaffold
  - `07-05` correction UI + point editor
- Keep eval gate logic in Python and fast to test.
- Keep UI optimistic but honest: no “alpha ready” badge unless the eval gate passes on a real gold set.
