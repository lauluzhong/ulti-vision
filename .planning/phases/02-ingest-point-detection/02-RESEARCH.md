# Phase 2: Ingest & Point Detection - Research

**Date:** 2026-04-23
**Phase:** 02-ingest-point-detection
**Scope:** INGEST-01, INGEST-02, POINT-01, POINT-03

## Executive Summary

Phase 2 should stay backend-first and establish three durable seams for later phases:

1. A single ingest service that accepts either a local file or an approved public URL and always produces the same normalized local artifact plus metadata.
2. A dedicated point-detection stage inserted between ingest and perception, with persisted point rows and boundary evidence.
3. A point-assignment contract that gives every downstream event both an absolute video timestamp and an in-point timestamp without requiring later phases to rediscover boundaries.

The safest plan is a 3-plan phase:
- ingest source expansion and rights logging
- point boundary detection + persistence
- point-aware pipeline/contract updates + tests

## Planning-Critical Findings

### 1. Unify file and URL ingest behind one service boundary

`src/sva/ingest/ingest.py` already owns the ingest baseline for local files: probe, CFR transcode, persist `jobs`, and compute windows. Phase 2 should preserve that as the single normalization path.

Recommended shape:
- add a source-resolver layer ahead of `ingest_clip()`
- `LocalFileSource` resolves directly to a filesystem path
- `RemoteUrlSource` validates allowlist + rights ack, downloads with `yt-dlp` to a working file, then hands that path into the same normalize/transcode path

Why this matters:
- avoids separate behavior for local vs URL input
- keeps VFR/CFR and metadata rules identical across sources
- makes Phase 6 async orchestration wrap one ingest contract instead of two

### 2. Point detection must persist first-class point rows

The current schema has nullable `events.point_id` but no point table. That is enough for Phase 1 placeholders, but not enough for Phase 2 because:
- point boundaries must exist before later phases run
- later correction needs point rows with start/end ranges
- `POINT-03` requires stable slicing semantics

Recommended schema additions:
- `points` table
  - `point_id`
  - `game_id`
  - `point_ordinal`
  - `start_video_ts_ms`
  - `end_video_ts_ms`
  - `confidence`
  - `boundary_evidence` JSONB
  - timestamps
- `rights_acks` table
  - `game_id` or pending ingest reference
  - `source_url`
  - `caller_id`
  - `acknowledged_at`

Recommended event contract changes:
- keep `video_ts_ms` as the absolute source-of-truth timestamp
- add explicit in-point offset (for example `point_video_ts_ms` or equivalent)
- make `point_id` non-null after Phase 2 assignment

### 3. Use staged fusion for boundary detection, not a monolithic model pass

The roadmap already locks the three-signal strategy:
- scoreboard OCR
- pull-detection heuristic
- cheap VLM Q&A

The lowest-risk implementation is staged fusion:
- run OCR and deterministic heuristics across the game timeline
- create candidate boundary intervals where score changed, pull began, or dead-time to live-play transition is detected
- use cheap VLM only on ambiguous intervals to choose between plausible boundaries or mark low confidence

Why this is preferable:
- cheaper than full-game VLM scanning
- easier to debug and test
- preserves evidence for future boundary editing UI

### 4. The Phase 2 API should be thin and synchronous

Roadmap success criteria call for API submission in Phase 2, but async orchestration belongs to Phase 6. The clean interpretation is:
- add a minimal FastAPI surface now for local file or URL ingest
- return normalized ingest metadata plus detected points
- keep jobs/polling/progress streaming out of scope for this phase

This prevents Phase 2 from silently absorbing queue/orchestrator work.

## Recommended Plan Shape

### Plan A: Source intake and rights-safe normalization
Cover:
- source abstraction for local file vs approved URL
- allowlist validation
- `yt-dlp` download path
- `rights_acks` persistence
- thin CLI/API surface over shared ingest service

Likely files:
- `src/sva/ingest/*`
- `src/sva/cli.py`
- `src/sva/api/*`
- migration for `rights_acks`
- tests for URL validation and rights enforcement

### Plan B: Point detection and persistence
Cover:
- point detector package/module
- boundary evidence schema
- `points` table migration and DAO
- staged fusion implementation
- fixtures and tests for known point boundaries

Likely files:
- new `src/sva/points/*` or equivalent
- migration for `points`
- pipeline insertion point
- tests for OCR/heuristic/VLM fusion behavior

### Plan C: Point-aware pipeline contracts
Cover:
- make pipeline produce point-scoped windows before interpret
- update `Event` contract and persistence for non-null `point_id` and in-point timestamp
- ensure SQL point filters work as a first-class query
- update end-to-end and DAO tests

Likely files:
- `src/sva/models.py`
- `src/sva/pipeline.py`
- `src/sva/events_dao.py`
- migration to tighten event point fields if needed
- tests for point-scoped persistence

## Verification Strategy

Phase 2 plans should prove all four requirement ids directly.

### INGEST-01
- API/CLI accepts `mp4`, `mov`, `m4v`, `webm`
- all sources land in the same normalized artifact path
- metadata row written for ingest

Suggested tests:
- unit tests for accepted extensions / rejection paths
- integration test for local file ingest through shared service

### INGEST-02
- only YouTube + UFA allowed
- rights ack mandatory
- authenticated/private URLs fail with explicit error

Suggested tests:
- URL allowlist table tests
- rights-ack required tests
- mocked `yt-dlp` failure tests

### POINT-01
- point detection runs before perception
- full-game input emits persisted point boundaries
- boundary evidence stored

Suggested tests:
- pipeline-order test proving point detection precedes perceive
- detector fixture test over a short full-game sample or synthetic boundary fixture

### POINT-03
- every persisted event carries non-null `point_id`
- event has in-point timestamp derived from point start
- DB query by `point_id` returns only that point's events

Suggested tests:
- DAO/integration test inserting point-scoped events
- pipeline e2e test verifying point assignment and point filter query

## Risks To Control During Planning

1. Do not let Phase 2 absorb Phase 6 queue/status work.
2. Do not let point ids be timestamp-derived if later correction needs stable ids.
3. Do not rely on whole-game VLM calls for point detection; use VLM as tie-breaker only.
4. Do not bolt URL ingest onto the CLI separately from the ingest service.
5. Do not leave boundary evidence ephemeral; it needs to be queryable later.

## Recommended Defaults For Planner

- prefer a dedicated `points` persistence layer over embedding boundaries only in `jobs.details`
- prefer one shared ingest service used by both CLI and FastAPI
- prefer a new point-detection module/package over hiding boundary logic inside `pipeline.py`
- prefer explicit in-point timestamp fields over burying them in `details`

## Research Outcome

Phase 2 does not need a phase split. It is best planned as three tightly scoped plans with clear data-boundary handoffs:
- source intake
- point detection
- point-aware contract propagation

The major architectural choice is already resolved by the context: backend-first ingest now, durable async orchestration later.
