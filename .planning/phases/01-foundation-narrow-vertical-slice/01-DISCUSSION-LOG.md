# Phase 1: Foundation & Narrow Vertical Slice - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-21
**Phase:** 01-foundation-narrow-vertical-slice
**Areas discussed:** Package layout

---

## Package Layout

| Option | Description | Selected |
|--------|-------------|----------|
| src/ layout | PEP 517 compliant, all packages under src/. Avoids accidental imports from repo root. | ✓ |
| Flat packages at root | ingest/, perceive/ etc. at repo root. Simpler but less strict import isolation. | |
| Single top-level package | sva/ at root without src/ wrapper. | |

**User's choice:** `src/` layout

---

| Option | Description | Selected |
|--------|-------------|----------|
| sva | Short for Sports Video Analytics. Imports: `from sva.ingest import Ingester`. | ✓ |
| ult | Short for Ultimate Frisbee. Domain-specific but less descriptive. | |
| pipeline | Describes the architecture literally. Generic name collision risk. | |

**User's choice:** `sva`

---

| Option | Description | Selected |
|--------|-------------|----------|
| One pkg per layer | sva/ingest/, sva/perceive/, sva/interpret/, sva/memory/, sva/api/ with adapters/ inside each. | ✓ |
| One pkg + shared core | Same but with explicit sva/core/ for shared schemas to avoid circular imports. | |
| You decide | Claude picks what prevents circular imports most cleanly. | |

**User's choice:** One package per layer (adapters inside each layer)

---

| Option | Description | Selected |
|--------|-------------|----------|
| sva/models.py | Single flat file at sva package root. No circular import risk. | ✓ |
| sva/ingest/models.py etc. | Each layer owns its models. Creates cross-layer import coupling. | |
| You decide | Claude picks the cleanest location. | |

**User's choice:** `src/sva/models.py`

---

## Claude's Discretion

- **DB**: Postgres + Docker Compose from Phase 1 (not SQLite). Avoids migration debt.
- **CLI**: Typer-based (`python -m sva.cli ingest clip.mp4 --model ... --fps ...`).
- **Langfuse**: Cloud free tier for Phase 1 (zero setup, one-line swap to self-hosted in Phase 6).
- **Memory stub**: Zero-retrieval with correct `retrieve()` interface signature.
- **Secrets**: `.env` + `python-dotenv` + Pydantic `BaseSettings` validated at import time.

## Deferred Ideas

- Langfuse self-hosted — deferred to Phase 6
- pgvector index tuning — deferred to Phase 5
- Makefile / `just` task runner — maybe later
- yt-dlp URL ingestion — Phase 2
