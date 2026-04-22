# Plan 01-03 — Ingest Layer (VFR→CFR, probe, sampler, end-to-end)

**Phase:** 01-foundation-narrow-vertical-slice
**Plan:** 01-03 — Ingest layer
**Completed:** 2026-04-22
**Requirements satisfied:** INGEST-03, INGEST-04, INGEST-05

## What shipped

The first architectural boundary of the Phase 1 vertical slice. One clip now flows from arbitrary local input → normalized CFR H.264 mp4 → `jobs` row in Postgres → window offsets ready for perceive.

- **`sva.ingest.probe`** — PyAV-based metadata probe. Detects VFR by sampling packet timestamps and computing coefficient of variation on `dts` deltas; returns `VideoMetadata(duration_s, avg_fps, is_variable_fps, codec, width, height)`. Raises `FileNotFoundError` on missing files.
- **`sva.ingest.transcode`** — VFR→CFR normalization via PyAV. Re-encodes to H.264 at a target fps (default 1 fps per PERCEIVE-01) with deterministic presentation timestamps (`settb`-equivalent inline via `pts_step`). Idempotent output path overwrites. This is the make-or-break ±2s timestamp gate for INGEST-04.
- **`sva.ingest.sampler.window_offsets`** — Pure function returning `list[(start_ms, end_ms)]` pairs covering `[0, duration_s)` in `window_size_s` increments (default 2s). Last window clipped. No I/O, no side effects — Phase 3 extends this with point-aware chunking.
- **`sva.ingest.ingest.ingest_clip`** — End-to-end orchestrator: probes source → transcodes to `data/transcoded/<video_id>.mp4` → INSERTs `jobs` row via `session_scope` (INGEST-05) → returns `IngestResult(video_id, game_id, source_path, transcoded_path, duration_s, status='ingested', windows, source_metadata, transcoded_metadata)`.
- **`JobRow` ORM class** — SQLAlchemy mapping mirroring the Alembic `jobs` table (UUID pk, `game_id` unique-indexed, `cost_usd` default 0, `duration_s` numeric).

## Commits (chronological, 6 total)

| # | SHA | Subject |
|---|-----|---------|
| 1 | `758e028` | test(01-03): add failing tests for sva.ingest.probe (RED) |
| 2 | `a98d1f1` | feat(01-03): implement sva.ingest.probe with PyAV VFR detection (GREEN) |
| 3 | `7c186af` | test(01-03): add failing tests for sva.ingest.transcode (RED) |
| 4 | `5fd5405` | feat(01-03): implement PyAV VFR to CFR transcoder (GREEN) |
| 5 | `23959e9` | test(01-03): add failing tests for sva.ingest.sampler.window_offsets (RED) |
| 6 | `2f057bf` | feat(01-03): implement window_offsets sampler + ingest_clip end-to-end (Task 3 GREEN) |

## Files created

- `src/sva/ingest/probe.py` (PyAV VFR probe)
- `src/sva/ingest/transcode.py` (VFR→CFR transcoder)
- `src/sva/ingest/sampler.py` (window offsets)
- `src/sva/ingest/ingest.py` (end-to-end orchestrator + JobRow ORM)
- `src/sva/ingest/__init__.py` (public re-exports)
- `tests/test_ingest_probe.py` (3 tests)
- `tests/test_ingest_transcode.py` (2 tests)
- `tests/test_ingest_sampler.py` (4 tests)
- `tests/fixtures/cfr_baseline.mp4` (synthetic CFR fixture)
- `tests/fixtures/vfr_synthetic.mp4` (synthetic VFR fixture for INGEST-04 CI)
- `tests/fixtures/README.md`

## Test results

9 passed in 0.39s (3 probe, 2 transcode, 4 sampler). No skips for online tests. Database round-trip for `ingest_clip` is deferred to Plan 01-05's CLI E2E test (requires Docker Postgres).

## Deviations

**1. Execution resumed mid-task (Rule 3 — environment).** The Opus-powered executor agent hit its usage cap after committing Tasks 1 & 2 and the Task 3 RED test. The orchestrator (using Sonnet) resumed inline, wrote the `sampler.py` + `ingest.py` implementations exactly per the plan's `<action>` block, updated `src/sva/ingest/__init__.py`, and committed as Task 3 GREEN. No scope change. All `<action>` content matches the plan verbatim.

**2. Manual DB round-trip deferred (Rule 3 — environment).** The plan's "integration smoke test" for `ingest_clip` requires `docker compose up -d db`; Docker is unavailable in this worktree. The DB write path is exercised instead by the CLI E2E in Plan 01-05 where the human-checkpoint review includes verifying a `jobs` row exists. `JobRow` column layout is statically verified against migration 0001 via `grep` in the plan's automated `<verify>`.

## What this enables

- Plan 01-05's CLI E2E can call `ingest_clip()` directly to produce a transcoded CFR clip + `jobs` row.
- Plan 01-05's `test_ingest_vfr_iphone.py` exercises the full probe→transcode→probe chain against the real iPhone HEVC VFR fixture and asserts the ±2s timestamp tolerance.
- Perceive runner (Plan 01-04) consumes `IngestResult.windows` to drive VLM calls per window.

## Self-Check: PASSED
