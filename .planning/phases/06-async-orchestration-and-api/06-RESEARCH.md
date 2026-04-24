# Phase 6: Async Orchestration & API - Research

**Researched:** 2026-04-24
**Domain:** Durable async video-job orchestration, HTTP API, partial progress, corrections write-path, and CSV export for the existing `sva` Postgres-backed pipeline. [VERIFIED: repo grep]
**Confidence:** MEDIUM

<user_constraints>
## User Constraints

- Keep the repo Postgres-first and consistent with existing contracts; the live codebase already centers `jobs`, `events`, `points`, `observations`, `memory_records`, and `corrections` on Postgres via SQLAlchemy and Alembic. [VERIFIED: user prompt] [VERIFIED: repo grep]
- Focus this phase on durable async job execution, resume-safe processing, job status persistence, partial progress surfacing, corrections API integration, and CSV export shape. [VERIFIED: user prompt] [VERIFIED: repo grep]
- Surface concrete risks, sequencing recommendations, and file targets instead of generic stack discussion. [VERIFIED: user prompt]
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| API-01 | `POST /ingest` submits file or URL and returns job id. [VERIFIED: repo grep] | Reuse existing upload/url validation in `src/sva/api/app.py` and `src/sva/ingest/ingest.py`, but return `202 Accepted` with `job_id == game_id` and enqueue a Dramatiq actor. [VERIFIED: repo grep] [CITED: https://github.com/fastapi/fastapi/blob/master/docs/en/docs/tutorial/request-files.md] [CITED: https://github.com/bogdanp/dramatiq/blob/master/docs/source/guide.md] |
| API-02 | `GET /jobs/:id` polls structured progress stages. [VERIFIED: repo grep] | Persist coarse job status on `jobs` plus per-point operational state in a new Postgres table; expose partial point summaries and counts from Postgres, not broker state. [VERIFIED: repo grep] [CITED: https://www.postgresql.org/docs/current/sql-select.html] |
| API-03 | `GET /games/:id/events` returns filterable per-game timeline. [VERIFIED: repo grep] | Extend existing `events_dao.list_event_rows(...)` filter seam into API serializers; the current DAO already filters by `point_id`, `event_type`, and `team`. [VERIFIED: repo grep] |
| API-04 | `POST /games/:id/corrections` accepts coach corrections. [VERIFIED: repo grep] | Wrap existing immutable `corrections_dao` + `memory.writer` seams in an API route; keep correction persistence append-only and trigger memory derivation without mutating `events`. [VERIFIED: repo grep] |
| API-05 | `GET /exports/:game_id.csv` downloads CSV event list. [VERIFIED: repo grep] | Build a versioned CSV serializer from persisted `events` rows and omit model-internal IDs from the user-facing export. [VERIFIED: repo grep] |
| EXPORT-01 | CSV export is one-row-per-event with stable documented columns. [VERIFIED: repo grep] | Freeze a v1 column order in code and test it directly; use `csv.DictWriter` with an explicit header list. [VERIFIED: repo grep] |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- The project-standard backend remains FastAPI on Python 3.12. [VERIFIED: repo grep]
- The orchestration style should stay lightweight; `CLAUDE.md` explicitly prefers plain Python async over LangGraph, and the repo already uses thin protocol seams instead of framework-heavy orchestration. [VERIFIED: repo grep]
- `CLAUDE.md` still contains an older memory-store sketch, but the implemented repo and Phase 5 context are now decisively Postgres-first; Phase 6 should follow the live Postgres contracts already in code instead of reviving a second primary store. [VERIFIED: repo grep]

## Summary

Phase 6 should treat the current `game_id` as the public `job_id`, keep Postgres as the canonical source of truth for job state, and use Dramatiq only for dispatch/retry mechanics. The existing code already persists the durable artifacts that matter for resume safety: `jobs` for coarse lifecycle, `points` for authoritative point boundaries, `observations` for cached VLM outputs keyed by `video_id/window_id/prompt_version_hash`, `events` for partial/final timeline rows, and `corrections` plus `memory_records` for the feedback loop. [VERIFIED: repo grep]

The critical design move is to add operational status tables and indexes around those artifacts instead of replacing them. `POST /ingest` should create or update the `jobs` row, enqueue a Dramatiq coordinator, and return immediately; the worker should then claim unfinished per-point work from Postgres, reuse persisted observations as the checkpoint boundary, persist events point-by-point, and update coarse plus per-point progress snapshots that `GET /jobs/:id` can serve directly. FastAPI `BackgroundTasks` is the wrong mechanism for this workload because the official docs position it for smaller same-process tasks and explicitly point heavier work toward a queue-backed system. [VERIFIED: repo grep] [CITED: https://github.com/fastapi/fastapi/blob/master/docs/en/docs/tutorial/background-tasks.md]

`POST /games/:id/corrections` should stay thin: validate request payload, snapshot the source event, write an immutable correction row through the existing DAO, and trigger the existing memory-writer seam. `GET /exports/:game_id.csv` should expose a deliberately small, versioned, coach-facing schema and never leak internal identifiers like `observation_id`, `event_id`, or `memory_refs`. [VERIFIED: repo grep]

**Primary recommendation:** Implement Phase 6 as `job_id == game_id`, Postgres-backed progress and resume state, Dramatiq for queue/retry only, and point-by-point persistence as the unit of visible partial progress. [VERIFIED: repo grep] [CITED: https://github.com/bogdanp/dramatiq/blob/master/docs/source/guide.md] [CITED: https://www.postgresql.org/docs/current/sql-select.html]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Ingest submission (`POST /ingest`) | API / Backend | Database / Storage | FastAPI should validate file/url input and create the job row; persistent state belongs in Postgres and the uploaded file lands on disk/object storage. [VERIFIED: repo grep] [CITED: https://github.com/fastapi/fastapi/blob/master/docs/en/docs/tutorial/request-files.md] |
| Queue dispatch and retries | API / Backend | Database / Storage | Dramatiq handles message delivery and retry policy, but job truth must remain queryable in Postgres because broker/result middleware does not model the repo's per-point status contract. [VERIFIED: repo grep] [CITED: https://github.com/bogdanp/dramatiq/blob/master/docs/source/guide.md] [CITED: https://github.com/bogdanp/dramatiq/blob/master/docs/source/advanced.md] |
| Resume-safe work claiming | Database / Storage | API / Backend | Claiming unfinished point work is a row-locking concern; Postgres `FOR UPDATE SKIP LOCKED` is the standard primitive for safe concurrent claiming. [CITED: https://www.postgresql.org/docs/current/sql-select.html] |
| Partial progress surfacing (`GET /jobs/:id`) | Database / Storage | API / Backend | The API should only serialize persisted status snapshots and partial event counts, not inspect in-memory worker state. [VERIFIED: repo grep] |
| Partial event timeline (`GET /games/:id/events`) | Database / Storage | API / Backend | Persisted `events` rows are already the canonical event timeline and already support the required filters in DAO form. [VERIFIED: repo grep] |
| Corrections write-path | API / Backend | Database / Storage | Request validation and route semantics live in FastAPI; immutable correction rows and derived memory rows belong in Postgres via existing DAOs. [VERIFIED: repo grep] |
| CSV export | API / Backend | Database / Storage | The API should stream a stable CSV generated from persisted event rows; no queue dependency is required for this read path. [VERIFIED: repo grep] |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.136.1 current on PyPI; repo floor is `>=0.115`. [VERIFIED: PyPI] [VERIFIED: repo grep] | HTTP routes for ingest, jobs, events, corrections, and exports. [VERIFIED: repo grep] | The repo already ships `src/sva/api/app.py` and FastAPI tests, and the official docs cover the exact `UploadFile` + form patterns already in use. [VERIFIED: repo grep] [CITED: https://github.com/fastapi/fastapi/blob/master/docs/en/docs/tutorial/request-files.md] |
| Dramatiq | 2.1.0 current on PyPI. [VERIFIED: PyPI] | Durable background dispatch, retries, and worker lifecycle for Phase 6 jobs. [VERIFIED: repo grep] | The roadmap explicitly calls for Dramatiq, and official docs show broker support, retries, and optional AsyncIO middleware without forcing a larger workflow platform. [VERIFIED: repo grep] [CITED: https://github.com/bogdanp/dramatiq/blob/master/docs/source/installation.md] [CITED: https://github.com/bogdanp/dramatiq/blob/master/docs/source/guide.md] |
| SQLAlchemy | 2.0.49 current on PyPI; repo already uses sync ORM/session patterns. [VERIFIED: PyPI] [VERIFIED: repo grep] | Canonical DAO and migration access to Postgres state. [VERIFIED: repo grep] | Every persisted subsystem in the repo already follows the same `Base` + ORM row + narrow DAO helper pattern; Phase 6 should extend that pattern instead of adding async ORM churn. [VERIFIED: repo grep] |
| psycopg | 3.3.3 current on PyPI; repo already depends on `psycopg[binary]`. [VERIFIED: PyPI] [VERIFIED: repo grep] | Postgres driver for API and workers. [VERIFIED: repo grep] | The repo already uses it through SQLAlchemy, and no phase requirement needs a second database driver. [VERIFIED: repo grep] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `dramatiq[redis]` | Install path documented by Dramatiq. [CITED: https://github.com/bogdanp/dramatiq/blob/master/docs/source/installation.md] | Redis-backed broker support for Dramatiq workers. [CITED: https://github.com/bogdanp/dramatiq/blob/master/docs/source/guide.md] | Use for queue transport only; do not move canonical job/progress state into Redis. [CITED: https://github.com/bogdanp/dramatiq/blob/master/docs/source/advanced.md] [VERIFIED: repo grep] |
| Python `csv` stdlib | Python 3.12 runtime. [VERIFIED: repo grep] | Stable one-row-per-event CSV export. [VERIFIED: repo grep] | Use for `GET /exports/:game_id.csv`; no extra dependency is needed for the Phase 6 export contract. [VERIFIED: repo grep] |
| `python-multipart` | Already declared in the repo. [VERIFIED: repo grep] | Multipart file uploads for `POST /ingest`. [VERIFIED: repo grep] | Keep using it for the existing file upload shape; do not switch request encoding in the same phase. [VERIFIED: repo grep] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| FastAPI `BackgroundTasks` | Dramatiq actor queue | FastAPI docs explicitly frame `BackgroundTasks` as a same-process tool and point heavier work toward a real queue backed by Redis or RabbitMQ; Phase 6 needs restart-safe work and long-running jobs. [CITED: https://github.com/fastapi/fastapi/blob/master/docs/en/docs/tutorial/background-tasks.md] |
| Dramatiq results middleware as job-status store | Postgres `jobs` + per-point status rows | Dramatiq's official results backends are Redis or Memcached, while the repo needs queryable per-point status and partial results that fit existing Postgres tables. [CITED: https://github.com/bogdanp/dramatiq/blob/master/docs/source/advanced.md] [VERIFIED: repo grep] |
| New `job_uuid` separate from `game_id` | `job_id == game_id` | A second top-level identifier adds translation code across `jobs`, `points`, `observations`, `events`, `corrections`, and API routes without adding functional value in the current schema. [VERIFIED: repo grep] |
| Async SQLAlchemy rewrite | Keep sync SQLAlchemy in API and worker code | The repo already uses sync engines, sessions, and DAOs everywhere; an ORM-mode rewrite would add risk without changing Phase 6 user-visible outcomes. [VERIFIED: repo grep] |

**Installation:**
```bash
uv add "dramatiq[redis]>=2.1.0"
```

**Version verification:** Current versions verified on 2026-04-24 from official PyPI JSON metadata. [VERIFIED: PyPI]
- FastAPI 0.136.1 published 2026-04-23. [VERIFIED: PyPI]
- Dramatiq 2.1.0 published 2026-03-03. [VERIFIED: PyPI]
- SQLAlchemy 2.0.49 published 2026-04-03. [VERIFIED: PyPI]
- psycopg 3.3.3 published 2026-02-18. [VERIFIED: PyPI]

## Architecture Patterns

### System Architecture Diagram

```text
client
  |
  | POST /ingest (file or URL)
  v
FastAPI route
  |
  | validate input -> save upload / validate URL -> create or update jobs row
  | return 202 { job_id = game_id }
  v
Dramatiq enqueue
  |
  v
coordinator actor
  |
  | ingest already persisted? -> yes: reuse
  | detect points if missing -> persist points
  | create / upsert per-point status rows
  v
Postgres claim loop
  |
  | SELECT next unfinished point FOR UPDATE SKIP LOCKED
  v
point worker
  |
  | for each window in point:
  |   observations cache hit? -> yes: reuse persisted observation
  |   no -> call Gemini -> persist observation checkpoint
  | interpret point -> persist events
  | update per-point status + aggregate jobs progress
  v
persisted partial state
  |
  +--> GET /jobs/:id -> job snapshot + per-point progress + partial counts
  |
  +--> GET /games/:id/events -> persisted event rows with point/type/team filters
  |
  +--> GET /exports/:game_id.csv -> versioned CSV built from persisted events
  |
  +--> POST /games/:id/corrections -> immutable correction row -> memory writer -> memory_records
```

### Recommended Project Structure

```text
src/sva/
├── api/app.py                # FastAPI app assembly and route wiring
├── api/contracts.py          # Request/response schemas for ingest/jobs/events/corrections/exports
├── jobs_dao.py               # Coarse job state + per-point operational status queries
├── queue.py                  # Dramatiq broker configuration and actor registration
├── orchestration.py          # Coordinator and resume-safe point processing loop
├── exports.py                # CSV schema/version constants and serializer
├── pipeline.py               # Pure stage helpers reused by worker code
├── events_dao.py             # Existing filter/read helpers extended for API serialization
├── ingest/ingest.py          # Existing ingest path reused by POST /ingest and workers
└── memory/                   # Existing corrections + writer seams reused by corrections API
```

### Pattern 1: Postgres Is the Job Status API
**What:** Persist both coarse job state and per-point operational state in Postgres, then have `GET /jobs/:id` read only from Postgres. [VERIFIED: repo grep]

**When to use:** Always for Phase 6 status, progress, partial results, and resume cursors. [VERIFIED: repo grep]

**Example:**
```python
# Source: https://www.postgresql.org/docs/current/sql-select.html
from sqlalchemy import text

CLAIM_SQL = text(
    """
    SELECT point_id
    FROM job_point_status
    WHERE game_id = :game_id
      AND status IN ('pending', 'running', 'retryable_error')
    ORDER BY point_ordinal
    FOR UPDATE SKIP LOCKED
    LIMIT 1
    """
)
```

- Recommended concrete shape: keep `jobs` for coarse lifecycle and add a dedicated `job_point_status` table keyed by `(game_id, point_id)` for mutable workflow state. [VERIFIED: repo grep] [CITED: https://www.postgresql.org/docs/current/sql-select.html]
- Keep `points` as the authoritative boundary model; do not overload boundary rows with retry/error bookkeeping. [VERIFIED: repo grep]

### Pattern 2: Observation Rows Are the Resume Checkpoint
**What:** Treat a committed observation row as the durable completion boundary for one VLM window, and always query cached observations before invoking Gemini. [VERIFIED: repo grep]

**When to use:** Every worker retry, restart, or resumed point run. [VERIFIED: repo grep]

**Example:**
```python
# Source: existing repo seam in src/sva/perceive/runner.py
cached = list_cached_observations(
    video_id=window.video_id,
    window_id=window.window_id,
    prompt_version_hash=prompt_hash,
)
if cached:
    return cached[0]
```

- Add a unique DB constraint on the cache key actually used by `run_window`: `(video_id, window_id, prompt_version_hash)`. The code already reads by that triple, but the schema does not yet enforce it. [VERIFIED: repo grep]
- Resume semantics should be phrased as "never re-run completed windows" rather than "never re-run an in-flight window that crashed before commit." The current architecture can guarantee the former at the DB boundary. [VERIFIED: repo grep]

### Pattern 3: Point-by-Point Partial Visibility
**What:** Persist and expose work one point at a time instead of waiting for the whole game to finish. [VERIFIED: repo grep]

**When to use:** `GET /jobs/:id` and `GET /games/:id/events` while a job is still running. [VERIFIED: repo grep]

**Example:**
```python
# Source: existing repo filters in src/sva/events_dao.py
rows = list_event_rows(
    game_id=game_id,
    point_id=point_id,
    event_type=event_type,
    team=team,
)
```

- Use persisted `events` as the partial timeline surface; do not invent a second transient event store for "work in progress". [VERIFIED: repo grep]
- Return point summaries from `job_point_status` and detailed rows from `events`; that keeps `GET /jobs/:id` cheap and `GET /games/:id/events` focused. [VERIFIED: repo grep]

### Pattern 4: Corrections API Is a Thin Wrapper Over Phase 5
**What:** Keep the public corrections route as request validation plus orchestration around the already-built correction and memory seams. [VERIFIED: repo grep]

**When to use:** `POST /games/:id/corrections`. [VERIFIED: repo grep]

**Example:**
```python
# Source: existing repo seam in src/sva/memory/writer.py
records = correction_to_memory_records(correction)
insert_memory_records(records)
```

- Persist the immutable correction row first, then derive memory rows from that stored snapshot. [VERIFIED: repo grep]
- Do not mutate `events` rows in place for coach feedback; the Phase 5 model intentionally keeps corrections append-only. [VERIFIED: repo grep]

### Anti-Patterns to Avoid

- **FastAPI `BackgroundTasks` for full game processing:** Official docs warn that heavier background computation should use a queue-backed tool rather than same-process tasks. [CITED: https://github.com/fastapi/fastapi/blob/master/docs/en/docs/tutorial/background-tasks.md]
- **Redis as the canonical status database:** Dramatiq's results support is Redis/Memcached-oriented and does not match the repo's queryable Postgres model for partial per-point progress. [CITED: https://github.com/bogdanp/dramatiq/blob/master/docs/source/advanced.md] [VERIFIED: repo grep]
- **Introducing a second identifier namespace:** Returning a fresh `job_uuid` separate from `game_id` will create translation bugs across routes and DAOs. [VERIFIED: repo grep]
- **Async ORM migration during the same phase:** The repo is uniformly sync-SQLAlchemy today; mixing async ORM conversion into the queue/API work would increase risk without directly satisfying any Phase 6 requirement. [VERIFIED: repo grep]

## Recommended File Targets

| Target | Change | Why This File |
|--------|--------|---------------|
| `src/sva/api/app.py` | Convert the single-route Phase 2 app into a route assembler for ingest, jobs, events, corrections, and exports. [VERIFIED: repo grep] | This is the existing FastAPI entrypoint and already owns `POST /ingest`. [VERIFIED: repo grep] |
| `src/sva/api/contracts.py` | Add typed request/response models for `POST /ingest`, `GET /jobs/:id`, `GET /games/:id/events`, `POST /games/:id/corrections`, and CSV metadata. [VERIFIED: repo grep] | The repo currently serializes ingest via ad hoc dict conversion; Phase 6 needs stable response contracts. [VERIFIED: repo grep] |
| `src/sva/jobs_dao.py` | New DAO for coarse job reads/writes and per-point status. [VERIFIED: repo grep] | The repo has no dedicated job DAO yet; `jobs` logic is currently split between `ingest`, `pipeline`, and observability cost helpers. [VERIFIED: repo grep] |
| `src/sva/orchestration.py` | New coordinator + resume loop that composes existing ingest, point detection, perceive, interpret, and persist seams. [VERIFIED: repo grep] | `src/sva/pipeline.py` already contains the stage order but is still a one-shot CLI path. [VERIFIED: repo grep] |
| `src/sva/queue.py` | New Dramatiq broker and actor declarations. [VERIFIED: repo grep] | This isolates worker bootstrapping from business logic and keeps API imports lightweight. [CITED: https://github.com/bogdanp/dramatiq/blob/master/docs/source/guide.md] |
| `src/sva/pipeline.py` | Refactor into smaller reusable stage helpers without changing canonical model contracts. [VERIFIED: repo grep] | The current function already encodes the correct high-level ordering and should be reused, not replaced wholesale. [VERIFIED: repo grep] |
| `src/sva/events_dao.py` | Add row-to-API serialization helpers and keep filter logic centralized. [VERIFIED: repo grep] | The required point/type/team filters already exist here. [VERIFIED: repo grep] |
| `src/sva/memory/corrections_dao.py` and `src/sva/memory/writer.py` | Reuse as-is behind the corrections route, with only minimal helper additions if API ergonomics require them. [VERIFIED: repo grep] | Phase 5 already delivered the persistence and derivation seams Phase 6 needs. [VERIFIED: repo grep] |
| `src/sva/exports.py` | New CSV schema/version constants and serializer. [VERIFIED: repo grep] | Export deserves a dedicated module so tests can lock column order and shape. [VERIFIED: repo grep] |
| `migrations/versions/0009_phase6_async_jobs_api.py` | Extend `jobs`, add `job_point_status`, and add the observation cache-key uniqueness/indexes. [VERIFIED: repo grep] | Phase 6 needs new operational state and stronger resume/idempotency guarantees. [VERIFIED: repo grep] |
| `tests/test_phase6_*.py` | New API, worker, migration, and export tests. [VERIFIED: repo grep] | Existing test layout is flat and phase-specific additions fit that pattern. [VERIFIED: repo grep] |

## Sequencing Recommendation

1. Land the migration and DAOs first: extend `jobs`, add `job_point_status`, and add the observation cache-key uniqueness/index. That creates the persistent contract every later API and worker step depends on. [VERIFIED: repo grep]
2. Refactor `src/sva/pipeline.py` into reusable stage helpers before adding Dramatiq actors. This keeps the worker implementation thin and reduces the chance of the API path and CLI path drifting apart. [VERIFIED: repo grep]
3. Add the queue layer and resume loop next: broker config, coordinator actor, claim-next-point query, and coarse/per-point status updates. Do not expose new API endpoints until this persistence path exists. [CITED: https://github.com/bogdanp/dramatiq/blob/master/docs/source/guide.md] [CITED: https://www.postgresql.org/docs/current/sql-select.html]
4. Expose `POST /ingest` and `GET /jobs/:id` after the worker path is real. Those two endpoints define the core client contract for the async job system. [VERIFIED: repo grep]
5. Add `GET /games/:id/events` once partial per-point event persistence is visible from real worker runs. Reuse the existing DAO filters instead of inventing query logic in the route. [VERIFIED: repo grep]
6. Add `POST /games/:id/corrections` and `GET /exports/:game_id.csv` last. They are thinner integrations over already-persisted data and Phase 5 seams. [VERIFIED: repo grep]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Long-running job execution | In-process threads or FastAPI `BackgroundTasks` | Dramatiq actors with broker-backed retries | FastAPI docs reserve `BackgroundTasks` for smaller same-process work; Phase 6 needs restart-safe execution. [CITED: https://github.com/fastapi/fastapi/blob/master/docs/en/docs/tutorial/background-tasks.md] |
| Concurrent work claiming | Python locks or local memory maps | Postgres `FOR UPDATE SKIP LOCKED` | Local locks fail across worker processes; Postgres row locking is the durable cross-process primitive. [CITED: https://www.postgresql.org/docs/current/sql-select.html] |
| Job results/progress storage | Redis-only result blobs | Postgres `jobs` + `job_point_status` + persisted `events` | The repo already queries Postgres artifacts directly and needs stable partial reads per point. [VERIFIED: repo grep] [CITED: https://github.com/bogdanp/dramatiq/blob/master/docs/source/advanced.md] |
| CSV bytes assembly | Manual string joins | `csv.DictWriter` with a frozen header list | Stable column order and quoting matter more than micro-optimizing a tiny export path. [VERIFIED: repo grep] |
| Correction handling | In-place `events` updates | Existing immutable `corrections` table and memory writer | Phase 5 explicitly modeled corrections as append-only audit records. [VERIFIED: repo grep] |

**Key insight:** The repo already has the durable business artifacts; Phase 6 should add operational state and route surfaces around them, not replace them with a separate queue-state architecture. [VERIFIED: repo grep]

## Common Pitfalls

### Pitfall 1: Treating broker state as the product API
**What goes wrong:** `GET /jobs/:id` becomes a thin wrapper around broker metadata or result middleware, so progress is incomplete, hard to query, and detached from persisted events. [CITED: https://github.com/bogdanp/dramatiq/blob/master/docs/source/advanced.md] [VERIFIED: repo grep]
**Why it happens:** Dramatiq does provide results middleware, which makes it tempting to reuse broker-side state for status pages. [CITED: https://github.com/bogdanp/dramatiq/blob/master/docs/source/advanced.md]
**How to avoid:** Store authoritative progress in Postgres and let the broker only deliver work. [VERIFIED: repo grep]
**Warning signs:** Job pages show "running" but cannot answer "which points are finished?" without calling the worker. [VERIFIED: repo grep]

### Pitfall 2: Returning a new `job_uuid` instead of the existing `game_id`
**What goes wrong:** Every downstream table needs translation between `job_uuid` and `game_id`, and route handlers start leaking both identifiers. [VERIFIED: repo grep]
**Why it happens:** API design often defaults to "job id" as a separate concept, but this repo already keys all durable artifacts by `game_id`. [VERIFIED: repo grep]
**How to avoid:** Define `job_id` as the external name for the existing `game_id` string in Phase 6 responses. [VERIFIED: repo grep]
**Warning signs:** New tables or responses carry both `job_id` and `game_id` for the same object. [VERIFIED: repo grep]

### Pitfall 3: Re-running perception after restart because the schema does not enforce the cache key
**What goes wrong:** Worker retries can duplicate observation rows or re-invoice Gemini for already-completed windows. [VERIFIED: repo grep]
**Why it happens:** `run_window()` already reads by `(video_id, window_id, prompt_version_hash)`, but the DB currently only guarantees uniqueness on `observation_id`. [VERIFIED: repo grep]
**How to avoid:** Add a unique index on the actual cache-key triple and resume from persisted observations. [VERIFIED: repo grep]
**Warning signs:** Multiple observation rows share the same `video_id/window_id/prompt_version_hash` but different `observation_id` values. [VERIFIED: repo grep]

### Pitfall 4: Mixing operational workflow state into domain tables without a boundary
**What goes wrong:** `points` or `events` rows accumulate retry counts, transient statuses, and worker errors that are not part of the domain model. [VERIFIED: repo grep]
**Why it happens:** Reusing existing tables feels faster than adding a dedicated operational table. [VERIFIED: repo grep]
**How to avoid:** Keep boundary truth in `points` and workflow mutability in `jobs` plus `job_point_status`. [VERIFIED: repo grep]
**Warning signs:** Boundary-correction work later has to reason about `retry_count`, `last_error`, or worker ownership on point rows. [VERIFIED: repo grep]

### Pitfall 5: Shipping an internal-facing CSV
**What goes wrong:** The CSV leaks `event_id`, `source_observations`, `memory_refs`, or other implementation details that coaches cannot use. [VERIFIED: repo grep]
**Why it happens:** Export code often mirrors the DB row shape by default. [VERIFIED: repo grep]
**How to avoid:** Freeze a small coach-facing schema and test the exact header list. [VERIFIED: repo grep]
**Warning signs:** The export serializer is built directly from `EventRow.__dict__` or `Event.model_dump()`. [VERIFIED: repo grep]

## Code Examples

Verified patterns from official sources:

### Dramatiq Redis Broker Setup
```python
# Source: https://github.com/bogdanp/dramatiq/blob/master/docs/source/guide.md
import dramatiq
from dramatiq.brokers.redis import RedisBroker

redis_broker = RedisBroker(url="redis://localhost:6379/0")
dramatiq.set_broker(redis_broker)
```

### Dramatiq Retry Options
```python
# Source: https://github.com/bogdanp/dramatiq/blob/master/docs/source/guide.md
import dramatiq

@dramatiq.actor(max_retries=5, min_backoff=1000, max_backoff=600000)
def process_game(game_id: str) -> None:
    ...
```

### FastAPI UploadFile + Form Pattern
```python
# Source: https://github.com/fastapi/fastapi/blob/master/docs/en/docs/tutorial/request-files.md
from fastapi import FastAPI, File, Form, UploadFile

app = FastAPI()

@app.post("/ingest")
async def ingest(
    upload: UploadFile | None = File(default=None),
    url: str | None = Form(default=None),
) -> dict[str, str]:
    ...
```

## CSV Export Shape

**Recommended Phase 6 CSV v1 columns:** `export_version`, `game_id`, `point`, `video_time_ms`, `video_timecode`, `event_type`, `team`, `turnover_subtype`, `throw_type`, `pass_direction`, `confidence`. [VERIFIED: repo grep]

- `export_version` must be the first column so downstream spreadsheet consumers can pin the schema explicitly. [VERIFIED: repo grep]
- `point` should expose `point_ordinal`, not `point_id`, because the current `point_id` is an internal synthetic identifier derived from `game_id`. [VERIFIED: repo grep]
- Do not include `event_id`, `observation_id`, `source_observations`, `memory_refs`, `rule_refs`, or `corrected_from_event_id` in the coach-facing CSV. [VERIFIED: repo grep]
- If additional detail is needed later, add a JSON export separately instead of widening the CSV with internal provenance fields. [VERIFIED: repo grep]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Synchronous `POST /ingest` returns a full ingest payload directly from FastAPI. [VERIFIED: repo grep] | Queue-backed `POST /ingest` should return immediately with `job_id == game_id`. [VERIFIED: repo grep] | Phase 6 roadmap dated 2026-04-24. [VERIFIED: repo grep] | Required for durable long-running jobs and client polling. [VERIFIED: repo grep] |
| One-shot CLI `run_pipeline()` marks the job complete only at the end. [VERIFIED: repo grep] | Phase 6 needs persisted stage and per-point progress snapshots while work is still running. [VERIFIED: repo grep] | Phase 6 roadmap dated 2026-04-24. [VERIFIED: repo grep] | Enables partial progress and resume-safe retries. [VERIFIED: repo grep] |
| Internal Phase 5 correction seam only. [VERIFIED: repo grep] | Public corrections API should wrap that seam without changing its append-only model. [VERIFIED: repo grep] | Phase 6 roadmap dated 2026-04-24. [VERIFIED: repo grep] | Keeps API thin and preserves correction provenance. [VERIFIED: repo grep] |

**Deprecated/outdated:**
- FastAPI `BackgroundTasks` for full game processing: outdated for this workload because official docs position it for smaller same-process tasks and suggest queue-backed tools for heavier work. [CITED: https://github.com/fastapi/fastapi/blob/master/docs/en/docs/tutorial/background-tasks.md]
- Separate Redis-only status truth: outdated for this repo because the codebase already standardizes on Postgres as the canonical persistence layer. [VERIFIED: repo grep] [CITED: https://github.com/bogdanp/dramatiq/blob/master/docs/source/advanced.md]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| None | No unverified planning assumptions were required for the recommended Phase 6 shape. | - | - |

## Open Questions

1. **Should `GET /games/:id/events` return partial persisted events before the whole job completes?**
   - What we know: The roadmap requires partial progress surfacing and the existing DAO can already read whatever event rows exist. [VERIFIED: repo grep]
   - What's unclear: The requirements do not explicitly say whether the events endpoint is only for completed games or can expose partial rows mid-run. [VERIFIED: repo grep]
   - Recommendation: Allow partial reads and include current job status in the response payload so the UI can distinguish "partial" from "final." [VERIFIED: repo grep]

2. **Do we need one actor per game or separate coordinator plus point actors?**
   - What we know: Dramatiq supports retries and broker-backed execution, and Postgres row claiming can safely coordinate multi-worker point processing. [CITED: https://github.com/bogdanp/dramatiq/blob/master/docs/source/guide.md] [CITED: https://www.postgresql.org/docs/current/sql-select.html]
   - What's unclear: The current codebase has no queue layer yet, so throughput and local operational complexity are not measured. [VERIFIED: repo grep]
   - Recommendation: Start with coordinator plus in-process point loop for simplicity, but keep the claim query and `job_point_status` schema compatible with a later fan-out to one actor per point. [VERIFIED: repo grep]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `.venv` Python | API, workers, tests | Yes | 3.12.13 | - |
| FastAPI | API routes | Yes | Installed in `.venv`; repo dependency `>=0.115`. [VERIFIED: repo grep] | - |
| Uvicorn | API serving | Yes | 0.45.0 | - |
| Pytest | Validation | Yes | 9.0.3 | - |
| Alembic | Migrations | Yes | 1.18.4 | - |
| ffmpeg | Video ingest/transcode tests | Yes | 8.1 | - |
| Postgres server | DB-backed tests and real queue/API progress state | No at the configured `DATABASE_URL` on localhost:5432. [VERIFIED: local command] | - | Start Postgres before implementation verification. |
| Dramatiq package | Queue layer | No in `.venv`. [VERIFIED: local command] | - | Install `dramatiq[redis]`. |
| Redis package/service | Dramatiq Redis broker | No local Python package; no local CLI/service detected. [VERIFIED: local command] | - | Install package and run a broker, or use RabbitMQ if Redis ops become a blocker. [CITED: https://github.com/bogdanp/dramatiq/blob/master/docs/source/guide.md] |
| Docker CLI | Local DB/Redis bring-up from `docker-compose.yml` workflows | No local CLI detected. [VERIFIED: local command] | - | Use external/local services directly. |

**Missing dependencies with no fallback:**
- Reachable Postgres is required to verify migrations, worker resume behavior, and DB-backed API tests. The current configured localhost Postgres was not reachable during research. [VERIFIED: local command]

**Missing dependencies with fallback:**
- Redis broker infrastructure is missing locally; RabbitMQ is an official Dramatiq alternative if Redis provisioning is a problem, but Postgres should still remain the canonical status store. [CITED: https://github.com/bogdanp/dramatiq/blob/master/docs/source/guide.md]

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest` 9.0.3 in `.venv`. [VERIFIED: local command] |
| Config file | `pyproject.toml` under `[tool.pytest.ini_options]`. [VERIFIED: repo grep] |
| Quick run command | `.venv/bin/pytest -q tests/test_phase6_ingest_jobs_api.py tests/test_phase6_orchestration.py tests/test_phase6_exports_api.py` |
| Full suite command | `.venv/bin/pytest -q` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| API-01 | `POST /ingest` validates source and enqueues async work | API integration | `.venv/bin/pytest -q tests/test_phase6_ingest_jobs_api.py::test_post_ingest_returns_job_id_and_enqueues` | No - Wave 0 |
| API-02 | `GET /jobs/:id` returns stage and per-point progress | API integration | `.venv/bin/pytest -q tests/test_phase6_jobs_api.py::test_get_job_returns_structured_progress` | No - Wave 0 |
| API-03 | `GET /games/:id/events` filters by point/type/team | API + DB integration | `.venv/bin/pytest -q tests/test_phase6_events_api.py::test_game_events_filters` | No - Wave 0 |
| API-04 | corrections API persists immutable correction and triggers memory writer | API + DB integration | `.venv/bin/pytest -q tests/test_phase6_corrections_api.py::test_post_correction_persists_and_derives_memory` | No - Wave 0 |
| API-05 | CSV route streams download | API integration | `.venv/bin/pytest -q tests/test_phase6_exports_api.py::test_export_endpoint_returns_csv` | No - Wave 0 |
| EXPORT-01 | CSV header order and one-row-per-event shape are frozen | unit | `.venv/bin/pytest -q tests/test_phase6_exports_api.py::test_csv_header_and_row_shape` | No - Wave 0 |

### Sampling Rate

- **Per task commit:** `.venv/bin/pytest -q tests/test_phase6_ingest_jobs_api.py tests/test_phase6_jobs_api.py tests/test_phase6_exports_api.py`
- **Per wave merge:** `.venv/bin/pytest -q`
- **Phase gate:** Full suite green plus a DB-backed restart/resume test that proves completed windows are not reprocessed after worker restart. [VERIFIED: repo grep]

### Wave 0 Gaps

- [ ] `tests/test_phase6_ingest_jobs_api.py` - enqueue contract and `job_id == game_id`
- [ ] `tests/test_phase6_jobs_api.py` - stage payload and partial progress shape
- [ ] `tests/test_phase6_orchestration.py` - resume-safe claim loop and observation-cache checkpoint behavior
- [ ] `tests/test_phase6_events_api.py` - filter behavior through the HTTP layer
- [ ] `tests/test_phase6_corrections_api.py` - corrections route wraps Phase 5 seams correctly
- [ ] `tests/test_phase6_exports_api.py` - CSV schema/version/header lock
- [ ] Postgres fixture coverage for new job-status tables
- [ ] Redis or broker test harness for enqueue smoke tests

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No for Phase 6 route design itself; the repo currently has no auth layer. [VERIFIED: repo grep] | Keep routes narrowly scoped and do not introduce broad list endpoints that would require identity before Phase 7. [VERIFIED: repo grep] |
| V3 Session Management | No | No session system exists in the repo yet. [VERIFIED: repo grep] |
| V4 Access Control | Yes | Constrain reads and writes by explicit `game_id`/`coach_id` request parameters and avoid cross-game or cross-coach list-all routes in Phase 6. [VERIFIED: repo grep] |
| V5 Input Validation | Yes | FastAPI request models, existing source validation, and Pydantic schemas should remain the validation boundary. [VERIFIED: repo grep] [CITED: https://github.com/fastapi/fastapi/blob/master/docs/en/docs/tutorial/request-files.md] |
| V6 Cryptography | No | No new crypto primitive is needed in this phase; continue using platform/database defaults. [VERIFIED: repo grep] |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Oversized or malformed upload payloads | Denial of Service | Keep file ingestion on the existing validated upload path and reject invalid source combinations early at the route boundary. [VERIFIED: repo grep] |
| URL ingest abuse / SSRF expansion | Information Disclosure | Keep the existing allowlist-driven URL validation and rights-ack policy in `src/sva/ingest/sources.py`. [VERIFIED: repo grep] |
| SQL injection in filters or claim queries | Tampering | Continue using SQLAlchemy parameter binding for DAO queries and `text()` statements. [VERIFIED: repo grep] |
| Duplicate job execution after retry | Tampering / DoS | Enforce DB-backed claim/update rules and observation cache-key uniqueness so retries resume from committed checkpoints. [VERIFIED: repo grep] [CITED: https://www.postgresql.org/docs/current/sql-select.html] |
| Cross-coach correction leakage | Information Disclosure | Keep corrections append-only, keyed by `coach_id`, and do not expose any list-all correction route in this phase. [VERIFIED: repo grep] |

## Sources

### Primary (HIGH confidence)

- `src/sva/api/app.py`, `src/sva/pipeline.py`, `src/sva/db.py`, `src/sva/ingest/ingest.py`, `src/sva/events_dao.py`, `src/sva/observations_dao.py`, `src/sva/memory/corrections_dao.py`, `src/sva/memory/writer.py`, `src/sva/models.py` - current contracts, persistence seams, and pipeline order. [VERIFIED: repo grep]
- `.planning/ROADMAP.md`, `.planning/REQUIREMENTS.md`, `.planning/PROJECT.md`, `.planning/phases/05-memory-correction-loop/05-CONTEXT.md` - Phase 6 goal, requirement IDs, user-facing constraints, and carry-forward seams. [VERIFIED: repo grep]
- FastAPI official docs:
  - https://github.com/fastapi/fastapi/blob/master/docs/en/docs/tutorial/request-files.md
  - https://github.com/fastapi/fastapi/blob/master/docs/en/docs/tutorial/request-forms-and-files.md
  - https://github.com/fastapi/fastapi/blob/master/docs/en/docs/tutorial/background-tasks.md
- Dramatiq official docs:
  - https://github.com/bogdanp/dramatiq/blob/master/docs/source/installation.md
  - https://github.com/bogdanp/dramatiq/blob/master/docs/source/guide.md
  - https://github.com/bogdanp/dramatiq/blob/master/docs/source/advanced.md
  - https://github.com/bogdanp/dramatiq/blob/master/docs/source/cookbook.md
- PostgreSQL official docs:
  - https://www.postgresql.org/docs/current/sql-select.html
- PyPI JSON metadata:
  - https://pypi.org/pypi/fastapi/json
  - https://pypi.org/pypi/dramatiq/json
  - https://pypi.org/pypi/sqlalchemy/json
  - https://pypi.org/pypi/psycopg/json

### Secondary (MEDIUM confidence)

- `.planning/research/SUMMARY.md` and `.planning/research/PITFALLS.md` - prior project research on why Phase 6 should avoid FastAPI `BackgroundTasks`, keep CSV human-facing, and preserve Postgres-first design. [VERIFIED: repo grep]

### Tertiary (LOW confidence)

- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Package versions and queue/API capabilities were verified against official docs and PyPI metadata. [VERIFIED: PyPI] [CITED: https://github.com/bogdanp/dramatiq/blob/master/docs/source/guide.md]
- Architecture: MEDIUM - The recommendation is strongly grounded in the live repo shape, but the exact coordinator-versus-fanout worker split remains an implementation choice. [VERIFIED: repo grep]
- Pitfalls: HIGH - The main failure modes come directly from the repo's current synchronous pipeline, official FastAPI/Dramatiq guidance, and the explicit Phase 6 requirements. [VERIFIED: repo grep] [CITED: https://github.com/fastapi/fastapi/blob/master/docs/en/docs/tutorial/background-tasks.md]

**Research date:** 2026-04-24
**Valid until:** 2026-05-24 for repo-structure guidance; re-check external package versions before implementation if work starts later than 30 days from this memo. [VERIFIED: PyPI]
