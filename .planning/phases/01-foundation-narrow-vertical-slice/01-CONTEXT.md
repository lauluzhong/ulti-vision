# Phase 1: Foundation & Narrow Vertical Slice - Context

**Gathered:** 2026-04-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Prove every architectural boundary end-to-end on one short clip (~90s, one point). Establish the swap-safe data contracts, VFR→CFR ingest, and Langfuse observability that every downstream phase depends on. No UI. No full-game processing. No complete event taxonomy — just one Event row in the DB as proof the pipeline runs.

Scope is strictly: INGEST-03 (CFR transcode), INGEST-04 (VFR fixture test), INGEST-05 (PyAV frame extraction), OBS-01 (Langfuse per-call trace), OBS-02 (cost-per-game aggregation).

</domain>

<decisions>
## Implementation Decisions

### Package Layout
- **D-01:** Use `src/` layout (PEP 517 compliant). All Python packages live under `src/`.
- **D-02:** Top-level package name is `sva` (Sports Video Analytics). Imports read: `from sva.ingest import Ingester`.
- **D-03:** One subpackage per pipeline layer: `src/sva/ingest/`, `src/sva/perceive/`, `src/sva/interpret/`, `src/sva/memory/`, `src/sva/api/`. Each layer contains its own `adapters/` subdirectory for swappable backends.
- **D-04:** Shared Pydantic schemas (`Observation`, `Event`, `MemoryRecord`) live in a single flat file: `src/sva/models.py`. This prevents circular imports (all layers import from `sva.models`, never from each other's model files). Can be split into `sva/models/` package if it grows past ~300 lines.

### Database
- **D-05 (Claude's Discretion):** Use Postgres + Docker Compose from Phase 1. Starting with SQLite and migrating is false economy — Phase 1 requires `cost_per_game` aggregation queries (OBS-02) and Phase 2 immediately needs point-scoped `WHERE point_id = ?` queries that benefit from Postgres's query planner. Migration debt is larger than Docker Compose setup cost. Provide a `docker-compose.yml` with Postgres 16. pgvector extension is installed from the start (needed in Phase 5) but not used until then.

### CLI Design
- **D-06 (Claude's Discretion):** Use [Typer](https://typer.tiangolo.com/) for the CLI. Invocation: `python -m sva.cli ingest clip.mp4 --model gemini-2.5-flash --fps 1`. Typer provides flag parsing, `--help` output, and type safety with near-zero boilerplate. A simple `python -m` script can't accommodate the `--model`, `--fps`, and `--dry-run` flags that will be needed across phases for rapid iteration. No `Makefile` targets for now — they add another layer of indirection during early development.

### Langfuse Observability
- **D-07 (Claude's Discretion):** Use Langfuse Cloud (free tier) for Phase 1. Zero-setup, accessible immediately, no Docker service to maintain alongside the DB. The SDK call is identical to self-hosted — swapping to a self-hosted Langfuse URL in Phase 6 (when prod infra is finalized) is a one-line config change. All traces must include: `video_id`, `model`, pipeline stage, token count, and cost. This satisfies OBS-01.

### Memory Stub
- **D-08 (Claude's Discretion):** Phase 1 memory retriever returns an empty list always (`[]`). It must implement the same interface (async `retrieve(query, tags, limit) -> list[MemoryRecord]`) that Phase 5 will fulfill. No SQLite stub, no hard-coded examples — zero-retrieval keeps the interface contract visible without polluting early outputs with fake examples.

### Environment & Secrets
- **D-09 (Claude's Discretion):** `.env` file + `python-dotenv` loaded at app startup. Secrets: `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `DATABASE_URL`. A `settings.py` (Pydantic `BaseSettings`) validates all required keys at import time so the developer gets a clear error before any network calls are made.

### Claude's Discretion
- DB: Postgres from day one (see D-05)
- CLI: Typer-based (see D-06)
- Langfuse: Cloud free tier for Phase 1 (see D-07)
- Memory stub: zero-retrieval with correct interface (see D-08)
- Secrets: `.env` + `python-dotenv` + Pydantic BaseSettings (see D-09)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements (Phase 1 scope)
- `.planning/REQUIREMENTS.md` — Read INGEST-03, INGEST-04, INGEST-05, OBS-01, OBS-02 for acceptance criteria. Also read PERCEIVE-01 (fps ceiling) and INTERPRET-02 (WFDF rules as data) for context on what Phase 1 schemas must anticipate.

### Research artifacts
- `.planning/research/STACK.md` — Full stack recommendations and rationale. Sections on Gemini 2.5 Flash, Claude Sonnet 4.5 prompt caching, PyAV vs ffmpeg-python, Langfuse, and per-game cost model are directly relevant to Phase 1.
- `.planning/research/ARCHITECTURE.md` — 5-package pipeline design with ASCII diagrams. The swap-safe adapter contract and data flow between layers define what Phase 1 must stub.
- `.planning/research/PITFALLS.md` — Read "VFR timestamp drift" (critical for INGEST-03/04), "per-window caching absent" (Phase 1 must not accidentally trigger VLM in a way that breaks Phase 3 caching), and "observability afterthought" pitfalls.

### Project context
- `.planning/PROJECT.md` — Key Decisions table (VFR→CFR, swap-safe adapters, Langfuse, WFDF as data, 1fps default / 3fps ceiling). Constraints section: cost visibility required from day 1.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield project. No existing components, hooks, or utilities.

### Established Patterns
- None yet. Phase 1 establishes the patterns all subsequent phases follow.

### Integration Points
- Phase 1 output: `Observation`, `Event`, `MemoryRecord` Pydantic models in `sva/models.py` and at least one `Event` row in Postgres. Phase 2 consumes ingest output; Phase 3 consumes the sampler; Phase 4 consumes Observations.

</code_context>

<specifics>
## Specific Ideas

- The VFR fixture for INGEST-04 success criterion should be an iPhone HEVC clip. If one isn't available, a synthetic VFR MP4 generated with ffmpeg (`-vf "settb=AVTB,setpts=N/FRAME_RATE/TB"`) can stand in for CI.
- The "±2 seconds" timestamp tolerance in INGEST-04 success criterion is a pass/fail gate, not a soft target — the test must assert this.
- OBS-02 (cost-per-game queryable) does not require a dashboard in Phase 1 — a `SELECT SUM(cost) FROM jobs WHERE game_id = ?` query returning a row is sufficient.

</specifics>

<deferred>
## Deferred Ideas

- **Langfuse self-hosted**: deferred to Phase 6 when prod infra is finalized. Phase 1 uses Cloud.
- **pgvector index tuning**: deferred to Phase 5. Extension installed in Phase 1 but no vectors yet.
- **Makefile / `just` task runner**: may be useful once the repo grows. Not needed in Phase 1.
- **yt-dlp URL ingestion**: explicitly out of Phase 1 (Phase 2 delivers it). Phase 1 accepts local file paths only.

</deferred>

---

*Phase: 01-foundation-narrow-vertical-slice*
*Context gathered: 2026-04-21*
