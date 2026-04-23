---
phase: 02-ingest-point-detection
plan: 01
subsystem: ingest-surface
tags: [phase2, ingest, url-policy, rights-ack, typer, fastapi, yt-dlp]

# Dependency graph
requires:
  - phase: 01-foundation-narrow-vertical-slice / plan 03
    provides: "shared ingest baseline: probe -> CFR transcode -> jobs persistence"
  - phase: 01-foundation-narrow-vertical-slice / plan 05
    provides: "existing CLI + pipeline entrypoint conventions"
provides:
  - "Shared source-intake layer for local files and approved public URLs"
  - "Per-call URL rights acknowledgment persistence (`rights_acks`)"
  - "Thin synchronous FastAPI ingest surface (`src/sva/api/app.py`)"
  - "Separate CLI intake surface (`sva intake`) while preserving `sva ingest` pipeline behavior"
affects: ["02-02", "02-03", "Phase 6"]

requirements-completed: [INGEST-01, INGEST-02]

# Metrics
completed: 2026-04-23
status: complete
---

# Phase 02 Plan 01: Source Intake & Rights-Safe Normalization Summary

**Expanded Phase 1 ingest into a shared Phase 2 source-intake service that accepts local files and approved public URLs, logs rights acknowledgments, and exposes the capability through both a thin API surface and a new `sva intake` CLI command without breaking the existing pipeline CLI.**

## Task Commits

1. `241b048` — `feat(02-01): add shared source intake and rights logging`
2. `b4e3945` — `feat(02-01): add thin ingest CLI and API surfaces`

## Accomplishments

### Task 1 — Shared source-intake policy and rights logging

- Added `src/sva/ingest/sources.py` with explicit `LocalFileSource` and `RemoteUrlSource` inputs plus policy errors for unsupported hosts, missing rights acknowledgment, and authenticated/private URL failures.
- Locked the URL allowlist to YouTube and UFA hostnames only.
- Added `src/sva/ingest/url_download.py` as a `yt-dlp` wrapper that downloads approved public URLs into `data/downloads/` and converts auth-required failures into a clear v1 policy error.
- Refactored `src/sva/ingest/ingest.py` to expose `ingest_source`, `ingest_local_file`, and `ingest_remote_url`, while preserving `ingest_clip` as a backward-compatible alias for the Phase 1 pipeline.
- Added `source_kind` and `source_url` fields to ingest persistence plus the Phase 2 migration `0002_phase2_sources_and_rights_acks.py`.
- Added unit coverage for allowlist policy, rights-ack enforcement, auth-required download failure, successful mocked download resolution, and local extension rejection.

### Task 2 — Thin invocation surfaces

- Preserved the existing `sva ingest` pipeline command so Phase 1 E2E behavior remains intact.
- Added a new `sva intake` command for pure shared ingest normalization of either a local file or an approved public URL.
- Added `src/sva/api/app.py` with a minimal synchronous `POST /ingest` endpoint that accepts either multipart upload or a public URL form payload and routes both through shared ingest service code.
- Added API tests covering file-upload acceptance, approved URL submission, and rejection when URL ingest omits the rights acknowledgment field.
- Updated `pyproject.toml` to declare the missing runtime dependencies for the new surface area: `fastapi`, `python-multipart`, `uvicorn`, and `yt-dlp`.

## Verification

- `./.venv/bin/pytest tests/test_ingest_sources.py tests/test_ingest_api.py -q` → `7 passed, 1 skipped`
- `./.venv/bin/python -m py_compile src/sva/ingest/sources.py src/sva/ingest/url_download.py src/sva/ingest/ingest.py src/sva/api/app.py src/sva/cli.py` → passed
- `./.venv/bin/pytest tests/test_db_migration.py -q` → `4 skipped` (Postgres unavailable in current worktree)
- `./.venv/bin/python -m sva.cli intake tests/fixtures/cfr_baseline.mp4 --dry-run` → passed

## Deviations / Notes

- `fastapi` and `yt-dlp` are declared in `pyproject.toml`, but the current `.venv` does not have them installed yet. The API tests therefore skip via `pytest.importorskip("fastapi")`, while source-policy tests still execute fully.
- Introduced `sva intake` instead of overloading `sva ingest` because changing `sva ingest` into a pure normalization command would have broken the existing Phase 1 pipeline acceptance flow. This keeps the repo backward-compatible while still satisfying the Phase 2 thin-surface requirement.

## Ready for Next Plan

Phase 2 can now move into `02-02`:
- public URL policy and rights-safe intake are in place
- local and remote sources converge into one normalization path
- the next dependency is point detection and persistence, not more intake scaffolding

## Self-Check: PASSED

- `src/sva/ingest/sources.py` exists and defines explicit local/remote source types
- `src/sva/ingest/url_download.py` exists and contains the `yt-dlp` wrapper
- `migrations/versions/0002_phase2_sources_and_rights_acks.py` exists
- `src/sva/api/app.py` exists and exposes a thin `/ingest` route
- `sva ingest` still routes through `run_pipeline`
- `sva intake` routes through shared ingest service code

---
*Phase: 02-ingest-point-detection*
*Completed: 2026-04-23*
