# Roadmap: Sports Video Analytics — Ultimate Frisbee

**Created:** 2026-04-20
**Granularity:** standard (5-8 phases)
**Core Value:** Turn existing, inconsistent-quality Ultimate Frisbee footage into a reliable per-point event timeline — without requiring the coach to watch the game.
**Coverage:** 45/45 v1 requirements mapped

## Strategic Shape

Per PROJECT.md, the timeline is staged: a fast feasibility prototype (weeks) proves the VLM+LLM+memory pipeline end-to-end before a ~2-month architecture-first build opens alpha to 2-5 friendly coaches. This roadmap reflects that shape.

- **Phase 1** is a narrow vertical slice: one ingested clip flows through schema → transcode → sampler → VLM → LLM with a memory stub → event row in the DB. The goal is to exercise every architectural boundary before broadening into each component. Observability, CFR transcode, and the swap-safe data contracts ship here because they gate everything downstream.
- **Phases 2–5** broaden each component to full v1 scope in dependency order (ingest+points → perceive → interpret → memory), honoring the research constraint that **memory must be alpha-ready before coaches arrive**.
- **Phase 6** converts the CLI pipeline into a durable async job behind a real API.
- **Phase 7** builds the evaluation harness that gates alpha and the minimal web UI that alpha coaches use. Alpha opens at the end of this phase, not before.

Non-negotiables honored: VFR→CFR transcode at ingest (Phase 1), per-window observation caching before any prompt iteration (Phase 3), per-event-type eval metrics before any accuracy claim (Phase 7), memory promotion requires 2+ distinct coaches (Phase 5), per-point decomposition architectural from Phase 2.

## Phases

- [x] **Phase 1: Foundation & Narrow Vertical Slice** - Swap-safe schemas, CFR transcode, observability, and a single-clip end-to-end CLI proof that every boundary works *(complete 2026-04-22)*
- [x] **Phase 2: Ingest & Point Detection** - Full file/URL ingest and point-boundary detection pass that gates every downstream per-point computation *(complete 2026-04-23)*
- [ ] **Phase 3: Perception Layer** - VLM adapter with structured Observation output and per-window caching so prompt iteration is cheap
- [ ] **Phase 4: Interpretation & Event Taxonomy** - LLM adapter with USAU-rule composition that emits the full v1 event set with schema-validated output
- [ ] **Phase 5: Memory & Correction Loop** - Model-agnostic memory store with tag+vector retrieval, scope-gated promotion, and a correction loop ready to absorb alpha feedback
- [ ] **Phase 6: Async Orchestration & API** - Dramatiq job queue, resume-on-crash workflow, full HTTP API surface, and CSV export
- [ ] **Phase 7: Evaluation Harness & Alpha UI** - Gold-set eval with per-event-type metrics, regression gate on memory promotions, and minimal coach-facing UI for upload, review, and correction — alpha opens here

## Phase Details

### Phase 1: Foundation & Narrow Vertical Slice
**Goal**: Prove every architectural boundary end-to-end on one short clip. Establish the swap-safe data contracts, CFR-transcoding ingest, and observability that everything downstream depends on.
**Depends on**: Nothing (first phase)
**Requirements**: INGEST-03, INGEST-04, INGEST-05, OBS-01, OBS-02
**Success Criteria** (what must be TRUE):
  1. A developer can run a CLI command on one short local clip (e.g. one point, ~90s) and observe that the pipeline ingests, CFR-transcodes (VFR input works), samples, calls the VLM, calls the LLM with a stubbed memory retriever, and writes at least one Event row to Postgres.
  2. An iPhone HEVC VFR fixture flows through ingest without timestamp drift — the resulting events carry timestamps within ±2 seconds of manually-verified values.
  3. Every VLM and LLM call has a persisted trace in Langfuse with `video_id`, `model`, pipeline stage, token count, and cost; the jobs table aggregates cost-per-game and it is queryable.
  4. Pydantic `Observation`, `Event`, and `MemoryRecord` models exist in code; switching the VLM backend string value changes only the adapter file, not the schema or any downstream consumer.
**Plans**: 01-01 schemas and swap-safe contracts; 01-02 infra, Postgres, Alembic, and config; 01-03 CFR ingest baseline; 01-04 adapters and observability; 01-05 CLI and narrow vertical slice pipeline
**UI hint**: no

### Phase 2: Ingest & Point Detection
**Goal**: Users can bring real Ultimate footage into the system from both file upload and public URL, and every subsequent computation is sliceable by point because boundaries are detected first.
**Depends on**: Phase 1
**Requirements**: INGEST-01, INGEST-02, POINT-01, POINT-03
**Success Criteria** (what must be TRUE):
  1. A user can submit a local mp4/mov/m4v/webm file or a public YouTube/UFA stream URL via the API and the system produces a normalized, transcoded video blob plus a metadata row on disk.
  2. For a full-game video, the system runs a dedicated point-boundary detection pass (scoreboard OCR + pull-detection heuristic + cheap VLM Q&A) that outputs a list of point boundaries before any per-point perception runs.
  3. Every event row persisted by downstream phases carries a non-null `point_id` and an in-point timestamp; SQL queries filtering `WHERE point_id = ?` return correctly scoped results.
  4. A URL ingestion path requires an explicit rights-acknowledgment flag from the caller before yt-dlp is invoked; the acknowledgment is logged.
**Plans**: 02-01 source intake and rights-safe normalization; 02-02 point detection and persistence; 02-03 point-aware pipeline contracts
**UI hint**: no

### Phase 3: Perception Layer
**Goal**: The system reliably converts windowed video clips into structured, model-agnostic `Observation` records without re-paying VLM cost when prompts or downstream code change.
**Depends on**: Phase 2
**Requirements**: PERCEIVE-01, PERCEIVE-02, PERCEIVE-03, PERCEIVE-04
**Success Criteria** (what must be TRUE):
  1. The sampler emits per-point windows at a configurable fps (default 1 fps aligned with Gemini 2.5 Flash native video sampling; 3 fps is the v1 ceiling); changing the fps value within that range is a single config change, and requests above 3 fps are rejected.
  2. Each window produces `Observation` records conforming to the versioned schema (`scene`, `disc`, `players`, `actions_detected`, `text_observed`, `confidence_overall`); the same window fed to a different VLM backend produces the same schema shape.
  3. Re-running perceive on a window whose `(video_id, window_id, prompt_version_hash)` already exists in cache returns the cached Observations without a new VLM call — Langfuse shows zero duplicate calls for the same triple.
  4. Gemini rate-limit responses trigger exponential backoff with cap; each call records latency and cost against the game_id and window_id.
**Plans**: 03-01 observations persistence and cache contract; 03-02 Gemini adapter and perception observability; 03-03 point-aware pipeline cache integration and verification
**UI hint**: no

### Phase 4: Interpretation & Event Taxonomy
**Goal**: The system produces the full v1 canonical event set — possession, goals, completions, turnovers, pass count, pass direction, throw type, point-level slicing — from Observations plus WFDF rules, with schema-validated output and honest `unknown` fallbacks.
**Depends on**: Phase 3
**Requirements**: INTERPRET-01, INTERPRET-02, INTERPRET-03, EVENT-01, EVENT-02, EVENT-03, EVENT-04, EVENT-05, EVENT-06, EVENT-07, EVENT-08
**Success Criteria** (what must be TRUE):
  1. Running interpret on a point's worth of Observations produces `Event` rows of every v1 type (`possession_start`, `completion`, `turnover`, `goal`, `point_end`) with team-level attribution, source observations, rule refs, and a closed enum `type` field.
  2. For any game, the stored events expose pass count per point and are queryable by point, by event-type, and by team; per-point filtering is a first-class SQL/API operation.
  3. Pass direction and throw type are emitted as best-effort with `"unknown"` as a first-class value; no event emits a confident direction when `scene.field_visible != "full"` — verified by a fixture clip with a zoomed-in camera.
  4. LLM output that fails the `Event` schema is logged and flagged via a dedicated validation error path; no schema-violating event silently reaches the events table.
  5. The WFDF rulebook is composed into the interpret prompt at call time from a single source file; swapping rule files at the next rulebook update is a data change, not a code change.
**Plans**: TBD
**UI hint**: no

### Phase 5: Memory & Correction Loop
**Goal**: The system stores, retrieves, and promotes model-agnostic memory records so coach corrections compound accuracy without any single coach's conventions leaking globally — making memory alpha-ready before coaches arrive.
**Depends on**: Phase 4
**Requirements**: MEMORY-01, MEMORY-02, MEMORY-03, MEMORY-04, MEMORY-05
**Success Criteria** (what must be TRUE):
  1. Rules, positive few-shot examples, negative few-shot examples, and coach corrections are stored in a single `MemoryRecord` schema that carries `kind`, `tags`, `scope`, `source`, `embedding_ref`, and `payload`; swapping the LLM leaves the records untouched.
  2. Interpret retrieves memory via a tag-filter-first + vector-rank-second query with a fixed budget (4-8 records) scoped to `global ∪ coach:<current>`; swapping the embedding provider requires a re-embed batch job but no schema migration.
  3. A submitted correction produces immutable records in the corrections table with full provenance (`coach_id`, `correction_id`, source event id, original VLM/LLM output) and spawns memory records at `scope: coach:<id>` by default — never `global`.
  4. Promotion of a memory record to `scope: global` hard-blocks unless at least 2 distinct `coach_id` values have corroborated the same correction pattern; during alpha a curator-review flag is required in addition. The enforcement is in code, not policy — a unit test verifies a single-coach loop cannot reach global.
**Plans**: TBD
**UI hint**: no

### Phase 6: Async Orchestration & API
**Goal**: The CLI pipeline becomes a durable, resumable, partial-streaming async job behind a real HTTP API, with CSV export, so a client can submit a game and poll to get a per-point timeline back.
**Depends on**: Phase 5
**Requirements**: API-01, API-02, API-03, API-04, API-05, EXPORT-01
**Success Criteria** (what must be TRUE):
  1. `POST /ingest` returns a `job_id` immediately and enqueues a Dramatiq job; `GET /jobs/:id` returns structured progress stages (ingest → point-detect → per-point perceive → interpret → persist) and partial per-point results as they complete.
  2. `GET /games/:id/events` returns a per-point event timeline filterable by `point`, `event_type`, and `team`; `POST /games/:id/corrections` accepts a coach correction against a specific event and triggers the memory writer.
  3. Killing the worker mid-game and restarting it does not re-invoke Gemini on completed windows — the DB shows each window was called exactly once; resume picks up from the first unfinished window.
  4. `GET /exports/:game_id.csv` returns a one-row-per-event CSV with stable, documented, versioned columns (no internal IDs like `observation_id` in the user-facing CSV).
**Plans**: TBD
**UI hint**: no

### Phase 7: Evaluation Harness & Alpha UI
**Goal**: With passing per-event-type eval metrics and a working coach-facing UI, the product is ready for 2-5 friendly coaches to upload real games and submit corrections that compound into memory. Alpha opens at the end of this phase.
**Depends on**: Phase 6
**Requirements**: UI-01, UI-02, UI-03, UI-04, UI-05, POINT-02, EVAL-01, EVAL-02, EVAL-03, EVAL-04
**Success Criteria** (what must be TRUE):
  1. A gold set of at least 3 full games (~40 points) is labeled by the builder plus an independent annotator, with inter-annotator agreement measured and recorded.
  2. The eval harness runs the pipeline with pinned model and prompt versions and reports per-event-type precision and recall separately — never a macro-average as the headline — plus an alpha-gate check (completion recall ≥ 85% AND completion precision ≥ 70% AND goals + possession-change recall ≥ 95%).
  3. Every `scope: global` memory promotion runs the eval harness and is hard-blocked if any event type's recall drops by ≥ 3 points; the gate is code-enforced, not a warning.
  4. A coach can open the web UI, upload a local file or paste a URL, watch progress stream per-point, view the per-point event list with timestamps that scrub the embedded video to the corresponding moment, see a stats dashboard (completion %, turnover count, goals, throw-type mix, pass count, per-point and per-game), and submit at least the four v1 correction types (flag wrong, re-classify type, mark missed, delete spurious) in three interactions or fewer.
  5. The video player hosts a point-boundary editor that a coach runs before the event timeline finalizes; correcting a boundary re-buckets downstream events to the corrected point_id.
**Plans**: TBD
**UI hint**: yes

## Progress Table

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation & Narrow Vertical Slice | 5/5 | Complete    | 2026-04-23 |
| 2. Ingest & Point Detection | 3/3 | Complete | 2026-04-23 |
| 3. Perception Layer | 1/3 | In progress | - |
| 4. Interpretation & Event Taxonomy | 0/TBD | Not started | - |
| 5. Memory & Correction Loop | 0/TBD | Not started | - |
| 6. Async Orchestration & API | 0/TBD | Not started | - |
| 7. Evaluation Harness & Alpha UI | 0/TBD | Not started | - |

## Coverage Summary

| Category | Count | Phases |
|----------|-------|--------|
| Ingest | 5 | Phase 1 (3), Phase 2 (2) |
| Points | 3 | Phase 2 (2), Phase 7 (1) |
| Perceive | 4 | Phase 3 (4) |
| Interpret | 3 | Phase 4 (3) |
| Memory | 5 | Phase 5 (5) |
| Events | 8 | Phase 4 (8) |
| API | 5 | Phase 6 (5) |
| UI | 5 | Phase 7 (5) |
| Export | 1 | Phase 6 (1) |
| Evaluation | 4 | Phase 7 (4) |
| Observability | 2 | Phase 1 (2) |
| **Total** | **45** | **All mapped** |

---
*Roadmap created: 2026-04-20*
*Last updated: 2026-04-23 — Phase 3 execution in progress; 03-01 and 03-02 complete, 03-03 next*
