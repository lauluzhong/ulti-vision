# Phase 6: Async Orchestration & API - Research

**Generated:** 2026-04-24
**Status:** Planning memo for implementation

## Summary

The repo is ready for Phase 6 because the synchronous control flow already exists in one place and the persistence seams needed for resume-safe execution are already real. `src/sva/pipeline.py` expresses the full ingest -> detect points -> perceive -> interpret -> persist loop, `src/sva/ingest/ingest.py` already anchors work on a canonical `jobs` row, and Phases 2-5 have made the major pipeline artifacts durable: points, observations, events, corrections, and memory records all persist independently. That means Phase 6 does not need to invent durability from scratch. It needs to factor the existing pipeline into explicit stages, persist enough progress detail to report status and resume honestly, and then expose thin HTTP routes over those services.

The main implementation tension is queue integration. The research and roadmap prefer Dramatiq + Redis for long-running jobs, but the current repo does not yet depend on Dramatiq. That is not a reason to blur the boundary or fall back to FastAPI background tasks. The right shape is: build an internal orchestration service that is deterministic and restart-safe from persisted state, then wrap it in a worker entrypoint that Phase 6 can call asynchronously. This keeps the queue framework thin, makes route tests easier, and prevents the worker choice from leaking into ingest, perception, interpretation, or memory code.

The other important Phase 6 truth is that "resume-safe" is mostly a data-model and stage-decomposition problem, not a worker magic problem. The repo already has three major anti-duplication anchors:
- ingest persists a job row and normalized video output
- point detection persists authoritative point rows
- perception persists observation cache keyed on `(video_id, window_id, prompt_version_hash)`

So Phase 6 should define explicit stage checkpoints around those existing persisted artifacts and avoid re-running work when the downstream truth already exists. The orchestration code should ask the DB what is done before calling Gemini or Claude again.

## Verified Repo Facts

- `src/sva/api/app.py` already has the thin FastAPI pattern and the current `/ingest` validation logic for one-of file-vs-url inputs.
- `src/sva/pipeline.py` is still synchronous, but it already separates the work into natural stages: ingest, point detection, perception per window, interpretation per point, event persistence, and final job completion.
- `src/sva/ingest/ingest.py` persists the canonical `jobs` row today, but the row only carries coarse status and total cost. Phase 6 will need richer stage/progress truth.
- `src/sva/observations_dao.py` and `src/sva/perceive/runner.py` already give the repo the most important resume lever: skip duplicate Gemini work when the exact observation cache triple already exists.
- `src/sva/events_dao.py` already supports filtered event reads by point, event type, and team, which means `GET /games/:id/events` can stay thin.
- Phase 5 already ships immutable corrections persistence plus coach-safe memory writing, so `POST /games/:id/corrections` should call those seams instead of creating a second correction path.
- The current dependency set includes FastAPI and Uvicorn but not Dramatiq or Redis client packages yet.

## Planning Conclusions

### 1. Split job lifecycle from queue wrapper

The first Phase 6 slice should create a durable orchestration service and richer job-progress persistence before or alongside queue integration. That avoids burying the core logic inside worker decorators and makes resume behavior testable from plain Python.

### 2. Treat persisted state as the only resume source of truth

The orchestration service should derive "what remains" from:
- `jobs` lifecycle/progress data
- existing persisted `points`
- existing cached `observations`
- existing stored `events`

Any in-memory worker-only progress flag would be drift-prone and should be avoided.

### 3. Keep API routes thin and canonical

Each Phase 6 route should delegate into one clear service:
- submit ingest/orchestration job
- read job status
- read canonical event timeline
- submit correction
- export canonical events

The API should not duplicate pipeline logic or embed queue internals in response payloads.

### 4. CSV export should be built from stored events, not recomputed pipeline output

The export surface should serialize the canonical `events` table into stable versioned columns. That keeps export deterministic and audit-friendly and avoids surprising divergence from `GET /games/:id/events`.

## Recommended Plan Split

### 06-01 — Durable job lifecycle and orchestration substrate

Extend the jobs/progress persistence surface and factor the synchronous pipeline into explicit stage-aware service functions that can resume from persisted truth.

### 06-02 — Async submission/status API and event reads

Upgrade `/ingest` to async job submission, add `GET /jobs/:id`, and expose canonical `GET /games/:id/events` filtering without reopening interpretation logic.

### 06-03 — Corrections API and CSV export

Add `POST /games/:id/corrections` as a thin wrapper over the Phase 5 correction path and implement `GET /exports/:game_id.csv` from canonical stored events.

### Optional 06-04 — Worker adapter and resumability verification

If Phase 6 is split more finely, isolate the queue-worker wrapper and crash/resume verification into its own plan so the queue framework stays thin and easy to replace.

## Risks to Watch

- **Fake async:** avoid FastAPI background tasks or ad hoc threads for multi-minute work; they are not durable enough for the pipeline's cost and runtime profile.
- **Duplicate perception cost:** resume logic must consult cached observations before calling Gemini again.
- **Status drift:** route payloads should reflect persisted stage truth, not transient worker logs.
- **API/service duplication:** do not fork a second ingest or correction path for the HTTP surface.
- **CSV leakage:** user-facing export should not include internal pipeline ids or raw provider fields.

## Immediate Recommendation

Plan Phase 6 around a thin orchestrator architecture:
- persisted job/progress truth first
- resumable stage execution second
- API wrappers third
- corrections/export surface last

That ordering keeps the public API thin and makes the future queue integration a wrapper instead of a rewrite.

---
*Phase: 06-async-orchestration-and-api*
*Research generated: 2026-04-24*
