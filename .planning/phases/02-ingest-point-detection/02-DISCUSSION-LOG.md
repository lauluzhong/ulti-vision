# Phase 2: Ingest & Point Detection - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-23
**Phase:** 02-ingest-point-detection
**Areas discussed:** URL ingest architecture, Point-boundary detection fusion, Upload + API surface, Point ID semantics

---

## URL ingest architecture

| Option | Description | Selected |
|--------|-------------|----------|
| YouTube + UFA only | Explicit allowlist for public video sources in v1 | ✓ |
| YouTube + UFA + direct public media URLs | Broader scope with more source variability | |
| Anything `yt-dlp` resolves | Maximum flexibility, weakest phase boundary | |

**User's choice:** Resumed from saved checkpoint — allowlist YouTube + UFA only.
**Notes:** Checkpoint also locked per-call rights acknowledgment, dedicated `rights_acks` logging, and loud failure for authenticated/private URLs.

---

## Point-boundary detection fusion

| Option | Description | Selected |
|--------|-------------|----------|
| Staged fusion (Recommended) | Scoreboard OCR first, pull/start heuristics second, cheap VLM only on ambiguous spans | ✓ |
| VLM-first detector | Run cheap VLM broadly, use OCR/heuristics as validation only | |
| Heuristic-only detector | Avoid VLM in Phase 2 and rely only on OCR + deterministic logic | |

**User's choice:** Auto-selected continuation default — staged fusion.
**Notes:** Keeps Phase 2 aligned with the roadmap wording while containing cost and preserving inspectable evidence for later correction.

---

## Upload + API surface

| Option | Description | Selected |
|--------|-------------|----------|
| Thin backend-first ingest surface (Recommended) | Shared service code with CLI parity and a synchronous local/API entrypoint | ✓ |
| Full async API now | Introduce job queue, polling, and partial results in Phase 2 | |
| CLI-only ingest | Defer all HTTP surface until Phase 6 | |

**User's choice:** Auto-selected continuation default — thin backend-first ingest surface.
**Notes:** This respects the Phase 2 boundary without pulling Phase 6 orchestration work forward.

---

## Point ID semantics

| Option | Description | Selected |
|--------|-------------|----------|
| First-class points + stable opaque ids (Recommended) | Persist point rows, keep stable ids, store both absolute and in-point timestamps | ✓ |
| Timestamp-derived ids | Encode point boundaries directly into ids | |
| Event-only point strings | Skip a dedicated point record and store `point_id` only on events | |

**User's choice:** Auto-selected continuation default — first-class points with stable ids.
**Notes:** Best fit for later point-boundary correction and for the `POINT-03` requirement that events remain sliceable by point.

---

## the agent's Discretion

- Confidence thresholds for detector fusion
- Exact route naming for the temporary synchronous HTTP surface
- Exact shape of persisted boundary-evidence payloads

## Deferred Ideas

None
