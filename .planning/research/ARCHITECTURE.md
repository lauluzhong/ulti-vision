# Architecture Research

**Domain:** Video-to-Events ML Pipeline (VLM + LLM + External Memory) — Ultimate Frisbee
**Researched:** 2026-04-20
**Confidence:** HIGH on component boundaries and data contracts (directly derived from the stated pipeline shape and constraints); MEDIUM on specific retrieval/sampling heuristics (sensible defaults; real numbers come from eval).

## Standard Architecture

### System Overview

```
┌───────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                  │
│   ┌──────────────┐      ┌───────────────────┐      ┌──────────────────┐    │
│   │  web UI      │      │  coach correction │      │  CSV / JSON      │    │
│   │  (upload,    │      │  interface        │      │  export          │    │
│   │   review)    │      │                   │      │                  │    │
│   └──────┬───────┘      └─────────┬─────────┘      └────────┬─────────┘    │
│          │                        │                         │              │
├──────────┴────────────────────────┴─────────────────────────┴──────────────┤
│                                API                                         │
│   ┌────────────────────────────────────────────────────────────────────┐   │
│   │  HTTP surface: POST /ingest, GET /jobs/:id, GET /games/:id/events, │   │
│   │                POST /corrections, GET /exports/:id                 │   │
│   └────────────────────────────────────────────────────────────────────┘   │
├────────────────────────────────────────────────────────────────────────────┤
│                       ORCHESTRATION (job queue)                            │
│   ┌────────────────────────────────────────────────────────────────────┐   │
│   │  durable workflow: ingest → detect_points → per-point: [sample →   │   │
│   │  perceive → interpret] → persist → notify                          │   │
│   └────────────────────────────────────────────────────────────────────┘   │
├────────────────────────────────────────────────────────────────────────────┤
│                           PIPELINE LAYER                                   │
│   ┌─────────┐  ┌─────────┐  ┌──────────────┐  ┌───────────┐  ┌─────────┐   │
│   │ ingest  │→ │ sampler │→ │  perceive    │→ │ interpret │→ │ events  │   │
│   │(video → │  │(frames, │  │ (VLM         │  │ (LLM      │  │ (store, │   │
│   │ frames) │  │ windows)│  │  adapter)    │  │  adapter) │  │  slice) │   │
│   └─────────┘  └─────────┘  └──────┬───────┘  └─────┬─────┘  └─────────┘   │
│                                    │                │                      │
│                                    │   (observations)   (rules,            │
│                                    │                ↕    examples,         │
│                                    │                     corrections)      │
│                                    │                │                      │
│                                    └────────┬───────┘                      │
│                                             ↓                              │
│                                      ┌─────────────┐                       │
│                                      │   memory    │ ← coach corrections   │
│                                      │ (rules, ex, │                       │
│                                      │ corrections,│                       │
│                                      │ retrieval)  │                       │
│                                      └─────────────┘                       │
├────────────────────────────────────────────────────────────────────────────┤
│                            PERSISTENCE                                     │
│   ┌─────────────────────────┐  ┌─────────────────────────────────────┐     │
│   │  Postgres (+ pgvector)  │  │  Object Store (videos, frames,      │     │
│   │  games, jobs, points,   │  │  sampled-frame bundles, thumbnails) │     │
│   │  events, observations,  │  │                                     │     │
│   │  memory, corrections,   │  │                                     │     │
│   │  rules, embeddings      │  │                                     │     │
│   └─────────────────────────┘  └─────────────────────────────────────┘     │
└────────────────────────────────────────────────────────────────────────────┘
```

**End-to-end pipeline plus memory feedback loop (single-diagram view):**

```
   ┌───────────┐
   │   VIDEO   │  (file upload or public URL)
   └─────┬─────┘
         ▼
   ┌─────────────┐   ┌─────────────┐   ┌──────────────┐    ┌──────────────┐
   │   ingest    │──►│  sampler    │──►│  perceive    │───►│  interpret   │
   │ (normalize, │   │ (~3 fps,    │   │ (VLM adapter │    │ (LLM adapter │
   │ metadata,   │   │  windows,   │   │  → Obs.List) │    │  Obs + rules │
   │ blob store) │   │ point-aware)│   │              │    │  + fewshots  │
   └─────────────┘   └─────────────┘   └──────┬───────┘    │  → Events)   │
                                              │            └──────┬───────┘
                                              │                   │
                                              ▼                   ▼
                                       ┌────────────┐      ┌─────────────┐
                                       │observations│      │   events    │
                                       │  (Postgres,│      │ (Postgres,  │
                                       │  audit trail│     │  per-point) │
                                       └────────────┘      └──────┬──────┘
                                                                  │
                                                                  ▼
                                                           ┌─────────────┐
                                                           │ web UI +    │
                                                           │ export CSV  │
                                                           └──────┬──────┘
                                                                  │
                                   coach correction (event id +   │
                                   clip_ref + fix)                │
                                                                  ▼
                                                           ┌─────────────┐
                                                           │  memory     │
                                                           │  writer     │
                                                           │  (promotes  │
                                                           │ correction →│
                                                           │ pos/neg ex, │
                                                           │ re-embeds)  │
                                                           └──────┬──────┘
                                                                  │
                    (next run retrieves new few-shot examples)    │
                                                                  ▼
                                                        back into `interpret`
```

### Component Responsibilities

| Component | Responsibility | Inputs | Outputs | Typical Implementation |
|-----------|----------------|--------|---------|------------------------|
| `ingest` | Accept video file/URL, normalize container/codec, probe metadata, store blob | `POST /ingest` (URL or upload) | `video_id`, metadata row, blob URI | FastAPI endpoint → ffmpeg probe → object storage put → Postgres row |
| `sampler` | Sample frames at configurable fps, group into windowed clips, attach timestamps, optionally adapt to activity | `video_id`, sampling config, optional point boundaries | `Window[]` (start/end ts, frame refs) | ffmpeg `-vf fps=3` → frames in object store → Postgres `windows` table |
| `perceive` | Call a VLM with a window's frames, parse structured output into `Observation` records | `Window`, VLM adapter choice | `Observation[]` persisted against `window_id` | Thin adapter class; Gemini/GPT-4o/Claude SDK; JSON-schema constrained output |
| `interpret` | Reconcile observations + rulebook + few-shot memory into canonical `Event[]` per point | `Observation[]`, retrieval results, rule bundle | `Event[]` persisted to `events` | LLM adapter with tool-use/JSON mode; deterministic rule validator wrapper |
| `memory` | Store rules, few-shot positives, few-shot negatives, coach corrections; expose retrieval by tag + vector similarity | writes: corrections, seed examples; reads: retrieval query | top-k `MemoryRecord[]` for interpretation | Postgres + pgvector; tag-filtered k-NN; boosted by recency and confirmations |
| `events` | Timeline store; per-point slicing; read API for UI/export | `Event[]`, queries by game/point/type | timeline JSON, CSV/Excel bytes | Postgres table + materialized view for per-point aggregates |
| `api` | Thin HTTP surface; enqueues jobs, streams status, serves events and corrections | HTTP requests | HTTP responses / SSE | FastAPI (or equivalent); auth later |
| `web` | Minimal UI: upload, job status, per-point event list, click-to-seek, correction form | HTTP from api | user actions | Next.js or SvelteKit — single app, no native |
| `orchestrator` | Durable job execution, retries, partial-progress emit | job submission | status events, final artifact pointers | Job queue (e.g. lightweight: Postgres-backed; heavier: Temporal/Prefect) |
| `eval` | Regression harness: run pipeline against gold set, compute precision/recall per event type | gold-set fixture, pipeline version | eval report row | CLI + Postgres `eval_runs` table |

**Failure modes per component:**

| Component | Likely failure | Symptom | Recovery |
|-----------|----------------|---------|----------|
| `ingest` | unsupported codec, corrupt file | probe fails | reject job with clear error; keep blob; allow re-submit after transcode |
| `sampler` | huge file OOMs, fps drift | frames missing | resumable sampling (by window), idempotent keys `window_id = hash(video_id, start, end, fps)` |
| `perceive` | rate limit / timeout / malformed JSON | window retries exhausted | exponential backoff; on JSON-parse failure, reprompt with stricter schema; mark window `degraded`, continue pipeline |
| `perceive` | VLM hallucinates events | observations contain impossible content | downstream validator (in `interpret`) drops observations failing schema constraints; `memory` rule "contradicts adjacent windows" demotes them |
| `interpret` | LLM contradicts rules (e.g. possession flip without turnover) | rule-validator rejects event | deterministic validator rejects; re-prompt with the violated rule as additional context (bounded retries); final fallback: emit `unknown` event with confidence=low |
| `memory` | retrieval returns junk (low-sim or off-tag) | poor interpretation | retrieval requires min-sim threshold + tag match; if empty, fall back to rules-only prompt (no few-shot) |
| `memory` | one coach's idiosyncratic corrections poison retrieval | recall drops for others | scope corrections to `source_coach_id` with per-coach vs. global promotion gate (see Correction-loop) |
| `events` | per-point slicing wrong because point detection failed | all events under a single giant "point 1" | point-boundary editor in UI — coaches correct boundaries; downstream events re-bucket |
| `orchestrator` | worker dies mid-game | job stuck | idempotent windows + resumable workflow; retries are cheap because window outputs are cached |
| `api` | long synchronous call | timeout | all heavy work is async job + status polling / SSE |
| `web` | incorrect event list | coach frustration | every event row has `clip_ref` so coaches can verify and correct in one click |

## Recommended Project Structure

```
repo/
├── apps/
│   ├── api/                     # FastAPI HTTP surface
│   │   ├── routes/
│   │   │   ├── ingest.py
│   │   │   ├── jobs.py
│   │   │   ├── events.py
│   │   │   ├── corrections.py
│   │   │   └── exports.py
│   │   └── main.py
│   └── web/                     # minimal web UI (upload, review, correct)
│       └── ...
├── packages/
│   ├── ingest/                  # video in, normalize, probe, store
│   ├── sampler/                 # frame sampling, window construction
│   ├── perceive/                # VLM adapters + observation schema
│   │   ├── adapters/
│   │   │   ├── gemini.py
│   │   │   ├── gpt4o.py
│   │   │   ├── claude.py
│   │   │   └── local_qwen.py
│   │   ├── schema.py            # Observation pydantic model (model-agnostic)
│   │   └── runner.py            # per-window execution
│   ├── interpret/               # LLM adapters + event reconciliation
│   │   ├── adapters/            # model-agnostic wrappers
│   │   ├── schema.py            # Event pydantic model
│   │   ├── rules/               # USAU-derived deterministic validators
│   │   ├── prompt.py            # prompt template builder
│   │   └── reconcile.py         # observation → event logic
│   ├── memory/                  # store + retrieval (model-independent)
│   │   ├── schema.py            # MemoryRecord pydantic model
│   │   ├── retriever.py         # tag + vector retrieval
│   │   ├── writer.py            # correction → record promotion
│   │   └── embeddings.py        # embedding provider adapter
│   ├── events/                  # timeline store + per-point views + export
│   ├── orchestrator/            # workflow definitions
│   │   └── workflows/
│   │       ├── process_game.py
│   │       └── apply_correction.py
│   └── common/                  # types, db, storage, config
├── rulebook/                    # USAU rules as structured YAML/JSON (seed memory)
├── eval/                        # gold set fixtures, harness, reports
│   ├── fixtures/
│   └── harness.py
├── infra/                       # docker compose, migrations, seed scripts
└── scripts/                     # dev tools (replay a window, dump memory, etc.)
```

### Structure Rationale

- **`packages/` split by pipeline stage, not by technology**: lets a solo dev mentally map a bug report ("wrong turnover at 12:34") to a single directory without crossing layers.
- **Adapters isolated to `perceive/adapters/` and `interpret/adapters/`**: every model-specific concern (SDK version, rate-limit handling, prompt formatting quirks) lives behind one interface. Swapping providers means editing one file and bumping config.
- **`memory/` has its own package and owns its schema**: memory is explicitly not imported transitively from `perceive` or `interpret` domain types; it has its own model-agnostic `MemoryRecord`. This is the physical manifestation of "memory survives model swaps."
- **`rulebook/` as data (YAML/JSON), not code**: rules evolve yearly (USAU rule updates). A coach or the builder can edit rule files without a code change; the `interpret.rules` module loads them.
- **`eval/` as a peer of the pipeline**: regression gating lives next to fixtures; easy to run locally before opening a PR to memory or prompts.
- **`orchestrator/workflows/` are small and readable**: the whole mental model of "what happens to a game" fits in one file.

## Architectural Patterns

### Pattern 1: Adapter + Model-Agnostic Schema (for VLM and LLM)

**What:** Each model provider is wrapped in a thin adapter that satisfies a `Perceiver` or `Interpreter` interface, returning a Pydantic-validated object that is identical regardless of provider.

**When to use:** Any boundary where the vendor will change (VLM providers, LLM providers, embedding providers).

**Trade-offs:**
- (+) Swapping providers is local to one file; memory and rules don't notice
- (+) Forces structured-output discipline (JSON schema / tool-use)
- (−) The schema has to be rich enough for all providers' strengths without being lowest-common-denominator
- (−) Some provider features (e.g. native grounding boxes) must be adapted into the common schema

**Sketch:**

```python
# packages/perceive/runner.py
class Perceiver(Protocol):
    def perceive(self, window: Window) -> list[Observation]: ...

class GeminiPerceiver:
    def perceive(self, window: Window) -> list[Observation]:
        raw = gemini_sdk.video_call(window.frames, RESPONSE_SCHEMA, PROMPT)
        return [Observation(**o) for o in raw["observations"]]

def run_window(window: Window, perceiver: Perceiver) -> list[Observation]:
    obs = perceiver.perceive(window)
    return [o for o in obs if observation_is_valid(o)]
```

### Pattern 2: Deterministic Rule-Validator Around a Non-Deterministic Core

**What:** `interpret` produces candidate events, then a deterministic USAU-rules validator accepts/rejects or annotates them. Violations are surfaced back as a constraint for a bounded re-prompt.

**When to use:** Any time an LLM produces state-change events in a rules-governed domain.

**Trade-offs:**
- (+) Catches "LLM contradicts rules" failures deterministically (e.g., possession flip without turnover event)
- (+) Rules live as data, not prompt text, so they can be unit-tested
- (−) Rule coverage is never 100%; validator must fail open (annotate, don't drop) for rules it can't evaluate

**Sketch:**

```python
# packages/interpret/reconcile.py
def reconcile(obs: list[Observation], memory_ctx: MemoryContext) -> list[Event]:
    candidates = llm.propose_events(obs, rules=rules.summary(), examples=memory_ctx.examples)
    validated = []
    for e in candidates:
        result = rules.validate(e, timeline=validated)
        if result.ok:
            validated.append(e)
        elif result.hard_violation:
            # one bounded re-prompt with violation as guidance
            continue
        else:
            e.warnings.append(result.note)
            validated.append(e)
    return validated
```

### Pattern 3: Memory as a Tagged Few-Shot Store with Retrieval Budget

**What:** `memory` stores records with `{kind, tags, embedding, payload, source, confidence, scope}`. `interpret` queries memory with a fixed retrieval budget (e.g. "at most 6 examples across positive/negative/rule at most 2 of each"). Retrieval is tag-filtered first, vector-ranked second.

**When to use:** When prompt size is bounded and example relevance varies strongly by event type.

**Trade-offs:**
- (+) Provider-agnostic (memory records are plain data; any LLM can consume them)
- (+) Prevents prompt bloat; cheap to reason about
- (+) Negative examples ("coach marked this NOT a turnover") are first-class
- (−) Tagging discipline required (but tags come for free from event types)
- (−) Embedding-provider change requires re-embedding (tolerable; batch job)

### Pattern 4: Async Job Workflow with Per-Window Idempotency

**What:** Everything is async. The processing workflow is `ingest → detect_points → fan out per-point → (per-window: sample → perceive → interpret) → merge → events`. Each window has an idempotent key; re-running is cheap.

**When to use:** Any ingest where wall-clock work exceeds a request timeout or where retries must be cheap.

**Trade-offs:**
- (+) 60-min games don't block HTTP
- (+) Partial results: can stream events per point as they finish
- (+) Retrying a bad point doesn't reprocess a whole game
- (−) Requires a durable queue; adds one infrastructure component

### Pattern 5: Correction as First-Class Data (not just a UI action)

**What:** A `Correction` is a durable record with `{event_id, original, corrected, clip_ref, source_coach_id, created_at, reason}`. Corrections never mutate events in place; the events table has `corrected_event_id` pointers. `memory.writer` turns corrections into memory records.

**When to use:** Any self-improving system where the correction-to-model loop must be auditable.

**Trade-offs:**
- (+) Full audit trail; can re-derive memory from corrections at any time
- (+) Enables per-coach vs. global scoping of corrections
- (−) Slightly more storage; one extra table

## Data Flow

### Request Flow (happy path)

```
[Coach]
   ├─ POST /ingest (url or file)  → api → orchestrator.enqueue("process_game", video_id)
   │                                                       ↓
   │                                            ingest.normalize → blob
   │                                                       ↓
   │                                            detect_points(video) → Point[]
   │                                                       ↓
   │                                  ┌───── per-point (parallel) ─────┐
   │                                  │  sampler.windows(point)        │
   │                                  │  for each window:              │
   │                                  │    perceive.run → Observation[]│
   │                                  │  interpret.reconcile(obs+mem) → Event[]
   │                                  └────────────────────────────────┘
   │                                                       ↓
   │                                            events.persist, notify
   ├─ GET  /jobs/:id                 → api → job status + partial per-point events
   ├─ GET  /games/:id/events         → api → events.read (grouped by point)
   ├─ POST /corrections              → api → corrections.persist → memory.writer.promote
   └─ GET  /exports/:id              → api → events.to_csv
```

### Correction Feedback Flow (end-to-end)

```
coach clicks "this is not a turnover, it's a completion" on event e_42
            │
            ▼
POST /corrections { event_id: "e_42", corrected: {...}, reason: "defender missed the D" }
            │
            ▼
corrections table INSERT (immutable audit row)
            │
            ▼
events table UPDATE e_42 (marked corrected, optionally insert corrected twin event)
            │
            ▼
memory.writer.promote(correction):
   - fetch clip_ref frames (or retrieve cached observations from window_id)
   - build TWO MemoryRecord rows:
       a) NEGATIVE: "observations of this shape SHOULD NOT produce turnover" (tag: turnover, neg)
       b) POSITIVE: "observations of this shape SHOULD produce completion" (tag: completion, pos)
   - scope: 'coach:<id>' initially; promote to 'global' after N≥3 coaches corroborate
   - embed the observation-context string; insert into pgvector
            │
            ▼
next run of `interpret`:
   - retrieval for "turnover candidate here?" now returns the new NEG example if similar
   - retrieval for "completion candidate here?" now returns the new POS example if similar
            │
            ▼
eval harness:
   - if there is a gold-set fixture that overlaps with this correction, re-run
   - compare before/after recall/precision; flag if a correction causes global regression
```

**Preventing one-coach overfitting:** memory records carry a `scope` field: `coach:<id>` (default) or `global`. Retrieval pulls `global + scope==current_coach`. A nightly/per-N-corrections job promotes a `coach:*` record to `global` when ≥K distinct coaches corroborate the same correction pattern (same tag, sufficiently similar embedding). Until promoted, one coach's idiosyncratic convention only affects their own jobs.

### Swap-Safety Contracts

Schemas below are Pydantic-shaped but language-neutral. They are the hard interface.

**`Observation` — emitted by `perceive`, consumed by `interpret` and `memory`.**

```jsonc
{
  "observation_id": "obs_01HYZ...",           // stable per (window_id, ordinal)
  "window_id": "win_01HYZ...",                // foreign key to sampler window
  "video_id": "vid_01HYZ...",
  "video_ts_start_ms": 732400,                // inclusive window start
  "video_ts_end_ms": 734400,                  // exclusive window end
  "observation_ts_ms": 733100,                // best-guess timestamp inside window
  "scene": {
    "field_visible": "partial" ,              // "full" | "partial" | "none"
    "camera": "sideline",                     // "sideline" | "endzone" | "elevated" | "handheld" | "unknown"
    "lighting": "ok",                         // "ok" | "harsh" | "dim"
    "obstruction": false
  },
  "disc": {
    "visible": true,
    "in_air": true,
    "possessor_team": "dark",                 // "dark" | "light" | "none" | "unknown"
    "possessor_role": "thrower"               // "thrower" | "receiver" | "defender" | "none"
  },
  "players": {
    "dark_count_visible": 4,
    "light_count_visible": 4
  },
  "actions_detected": [                       // free-form VLM-reported action tags
    {"tag": "throw", "confidence": 0.8},
    {"tag": "catch_attempt", "confidence": 0.6}
  ],
  "text_observed": [                          // OCR hints (scoreboard, jersey text)
    {"text": "DARK 4 LIGHT 3", "kind": "scoreboard", "confidence": 0.9}
  ],
  "free_form_note": "thrower releases flick to space near far sideline",
  "model": { "provider": "gemini", "model_id": "gemini-3", "version": "..." },
  "confidence_overall": 0.72,
  "raw_response_ref": "s3://.../raw/win_01HYZ.json"
}
```

Why these fields survive model upgrades:
- Nothing is shaped like a specific model's output (no Gemini-only grounding box keys; no GPT-only segment ids).
- Scene/disc/players/actions are conceptual features of Ultimate that any competent VLM can describe.
- `free_form_note` preserves model-specific insight as a string that any future LLM can re-interpret.
- `model` block is metadata, not identity — events refer to `observation_id`, not to the model.
- `raw_response_ref` keeps the provider's original payload for forensics without leaking it into contracts.

**`Event` — emitted by `interpret`, the canonical per-point output.**

```jsonc
{
  "event_id": "evt_01HYZ...",
  "game_id": "game_01HYZ...",
  "point_id": "pt_01HYZ...",
  "point_ordinal": 5,                         // 1-indexed within game
  "video_ts_ms": 733100,
  "type": "completion",                       // one of a closed enum (see below)
  "team": "dark",                             // team performing the event
  "player_id": null,                          // always null in v1 per PROJECT scope
  "details": {
    "throw_type": "backhand",                 // best-effort, nullable
    "pass_direction": "down_field",           // "up_field" | "down_field" | "lateral" | "unknown"
    "outcome": "caught"                       // event-type-specific
  },
  "source_observations": ["obs_01HYZ...", "obs_01HYZ..."],
  "rule_refs": ["USAU-XIV.A"],                // rules used/enforced while producing this event
  "memory_refs": ["mem_01HYZ..."],            // few-shot records retrieved into the prompt
  "confidence": 0.78,
  "warnings": [],                             // rule-validator annotations, non-fatal
  "corrected_from_event_id": null,            // if this event replaces a prior one
  "model": { "provider": "anthropic", "model_id": "claude-4.7", "version": "..." }
}
```

Closed `type` enum (v1): `possession_start`, `possession_end`, `completion`, `turnover`, `goal`, `point_end`, `unknown`. Future types are additive, never renames.

Why this schema survives model upgrades:
- `source_observations` keeps traceability intact; replacing the LLM only rewrites the function from obs→event, not the shape of event.
- `rule_refs` and `memory_refs` are model-independent pointers.
- `details` is typed per-event-kind but deliberately sparse; rich future attributes land in `details` without migrations.

**`MemoryRecord` — stored in `memory`, retrieved by `interpret`.**

```jsonc
{
  "memory_id": "mem_01HYZ...",
  "kind": "few_shot_positive",                // "few_shot_positive" | "few_shot_negative" | "rule" | "correction"
  "tags": ["turnover", "drop"],               // at minimum the relevant event type
  "scope": "global",                          // "global" | "coach:<id>" | "team:<id>"
  "source": {
    "origin": "correction",                   // "seed" | "correction" | "eval" | "manual"
    "source_coach_id": "coach_123",           // if from correction
    "source_correction_id": "cor_01HYZ...",
    "source_event_id": "evt_01HYZ..."
  },
  "embedding_ref": "vec_01HYZ...",            // pointer to pgvector row; embedding provider metadata
  "embedding_input": "thrower releases flick, defender skies receiver, disc on ground",
  "payload": {
    // for few-shot: the observation-context + the expected/unexpected event
    "context_observations_summary": "...",
    "expected_event": { "type": "completion", "details": { "throw_type": "backhand" } },
    "rationale": "defender did not establish possession; disc retained by offense"
  },
  "confidence": 0.9,                          // seed-level; can rise with corroboration
  "corroborations": 2,                        // count of distinct coaches/events that confirm
  "created_at": "2026-04-20T10:00:00Z",
  "last_used_at": "2026-04-19T22:15:00Z"
}
```

**Retrieval interface (memory):**

```python
# packages/memory/retriever.py
def retrieve(
    query: RetrievalQuery,                 # has: event_candidate_type, context_text,
                                           #       current_coach_id, budget
) -> list[MemoryRecord]:
    # 1) Hard filter: tags contain query.event_candidate_type
    #                 AND scope in {"global", f"coach:{query.current_coach_id}"}
    # 2) Vector rank: cosine(embedding, query.context_text_embedding) >= MIN_SIM
    # 3) Diversity: at most N positives, M negatives, K rules within `budget`
    # 4) Recency bonus: slight boost for records with corroborations >= 2
    ...
```

This means swapping the LLM does not change what `retrieve` returns; swapping the embedding model requires a re-embed job but not a schema change.

### State Management

Memory and events are server-owned; the client is stateless beyond session. The UI subscribes to job status via polling or SSE; the source of truth for events is always the server.

### Key Data Flows

1. **Game processing:** video → ingest → sampler → (per-window) perceive → interpret (with memory retrieval) → events → UI
2. **Correction feedback:** UI correction → corrections table → memory.writer → memory record(s) → retrieved by next interpret call
3. **Rule application:** seed rules YAML → memory.seed (as `kind=rule` records) + interpret.rules.validator (code path). Rules live in two forms: (a) prompt-surfaced "rule" memory records retrievable by tag, (b) deterministic validators that run after interpret. Composition: retrieval inserts relevant rules into the prompt, validator enforces hard ones regardless of the LLM.
4. **Eval regression:** gold-set fixture → run pipeline with pinned models → compare events-predicted vs. events-labeled → per-event-type P/R → eval_runs row
5. **Model swap:** change config `perceive.provider=X` or `interpret.provider=Y` → re-run (or partially re-run from `perceive` onward) → memory untouched, contracts unchanged

### Video Processing Topology — explicit choices

- **Async, not synchronous.** 60-minute game cannot block a request. `POST /ingest` returns a `job_id` immediately; clients poll `GET /jobs/:id` or subscribe to SSE.
- **Partial results per point.** As soon as a point's events are persisted, the UI can show them. Users review from the top while later points are still processing.
- **Resume on failure.** Window-level idempotency means a crashed worker restarts from the first unfinished window. `point_id` aggregation is deterministic from window outputs.
- **Retry policy.** VLM calls: 3 retries with exponential backoff, 1 "strict JSON" re-prompt, then mark window `degraded`. Degraded windows do not block the point; interpret runs on whatever observations exist and surfaces a warning on affected events.

### Per-Point Decomposition — explicit choice

**Detect points first, then process per-point.** Rationale:

- Error containment: a bad point doesn't poison neighboring ones.
- Parallelism: 12–20 points per game → natural fan-out unit.
- Rerun granularity: a coach saying "point 7 looks wrong" triggers re-running one point, not the whole game.
- Interpretation quality: LLM reasons much better when context is bounded to "everything that happened on this point" than when streamed continuously.

Point detection is its own small pipeline step: it runs first, uses a cheap pass (scoreboard OCR + pull-detection heuristics + VLM Q&A on ~1 fps sampled frames). Detected boundaries become editable in the UI — coaches can correct boundaries just like they correct events, and downstream events re-bucket.

Trade-off: if point detection is wrong upstream, every event under that "point" is misattributed. Mitigation is the point-boundary editor (cheaper than getting point detection perfect) plus a rule-validator check "number of goals per point == 1" that flags suspicious boundaries.

### Frame Sampling Strategy — explicit choice

**Start with fixed ~3 fps. Add adaptive sampling only if eval shows recall drops on fast action.**

- Fixed sampling is radically simpler, trivially reproducible, trivially cost-modeled.
- Adaptive sampling requires an activity detector — which is itself a model — which has its own failure modes.
- If/when adaptive is needed: a very cheap signal (frame-diff magnitude, optical-flow proxy, audio-energy from play calls) bumps fps to 5–6 for 2–3 seconds around detected motion. Deterministic, no new model dependency.
- Cost coupling: sampling rate drives VLM call volume linearly. The sampler is the one place to tune cost-per-game. Expose as config.

### Memory Retrieval at Interpretation Time — explicit choice

- **Tag-filter first, vector-rank second, diversity-cap third.** Tag filter ensures "only retrieve turnover examples when evaluating a turnover candidate." Vector rank orders within tag. Diversity cap prevents five near-duplicate positives from crowding out one crucial negative.
- **Retrieval budget: 4–8 records per event candidate**, enforced. Keeps prompt size predictable; keeps LLM from drowning.
- **Always include top-1 retrieved rule** (if any rule record has the event type tag). Rules are cheap tokens and reliable anchors.
- **Scope-aware:** `global ∪ coach:current_coach`. Prevents cross-coach noise; allows per-coach customization.
- **No RAG re-ranking in v1.** Not worth the complexity; revisit only if eval shows retrieval quality is the bottleneck.

### State and Persistence — explicit choice

**One Postgres (with pgvector) + one object store. That's it.**

- **Postgres:** `videos`, `jobs`, `points`, `windows`, `observations`, `events`, `corrections`, `memory`, `rules`, `eval_runs`, `users`, `coaches`.
- **pgvector extension:** `memory_embeddings(memory_id, embedding)` and similar for observation-context embeddings if needed.
- **Object store (S3-compatible or local filesystem in dev):** original videos, sampled-frame bundles (tiled), raw VLM responses, exports.

Deliberately excluded for solo-build simplicity:
- No separate vector DB (pgvector is enough at this scale; 10k memory records and ≤1M observations fit easily)
- No Redis in v1 (Postgres LISTEN/NOTIFY or a Postgres-backed queue covers job signaling)
- No search DB (Postgres full-text covers notes/search for a long time)

If/when scale demands it, the natural split is: move vector ops to a dedicated vector DB, or move job queue to a dedicated workflow engine. Neither is needed for alpha.

### Build Order (architecture-first, mapped to phases)

The minimum end-to-end "hello world" that proves the architecture is:

> One public UFA YouTube clip (single point, ~90 seconds) goes in. Three events come out in a CSV. A coach (or the builder) corrects one event. Next run on the same clip reflects the correction.

That loop exercises every boundary. Build order:

1. **Scaffold persistence + contracts.** Postgres schemas for `videos`, `windows`, `observations`, `events`, `memory`, `corrections`. Pydantic models for `Observation`, `Event`, `MemoryRecord`. No UI, no auth, no queue.
2. **`ingest` + `sampler`, sync, local only.** ffmpeg-based. CLI entrypoint: `gsd ingest <url>` puts frames in blob store and rows in DB.
3. **`perceive` with one VLM adapter (Gemini or Claude).** CLI: `gsd perceive <window_id>`. Writes `observations`.
4. **`interpret` with one LLM adapter + rules as data.** CLI: `gsd interpret <point_id>`. Writes `events`. Memory retrieval is a stub that returns [] — prove the pipeline works with rules-only first.
5. **`memory` writer and retriever.** Seed ~20 hand-crafted few-shot records for the four MVP event types. `interpret` now reads from memory.
6. **`orchestrator` workflow + job queue.** Wrap steps 2–5 into one durable workflow. API endpoints wrap the workflow.
7. **Minimal UI.** Upload form, job-status page, per-point event list with click-to-seek, correction form.
8. **`memory.writer.promote`.** Correction → memory records. The loop closes.
9. **Point detection.** Real point-boundary detection; editable in UI.
10. **Eval harness.** Gold set fixture (~10 points, human-labeled), regression script in CI-or-pre-PR.
11. **Second VLM adapter + second LLM adapter.** Prove swap-safety under actual swap.
12. **Hardening:** retries, degraded-window handling, export, cost dashboard, observability (see below).

**Rationale:** Each step adds one component or one contract. Steps 1–5 prove the read path on a single game; step 8 proves the write/feedback path; step 11 is the acid test that the contracts really are swap-safe. Alpha gate requires steps 1–12 plus eval hitting ~85% recall.

### Observability and Evaluation Infrastructure

Minimum useful eval harness (fits alongside, not inside, the pipeline):

- **`eval/fixtures/`**: gold-set fixtures — ~10 points to start, each with (video URL or clip ref, window of video_ts, labeled events list). JSON files, committed.
- **`eval/harness.py`**: runs the pipeline against each fixture with pinned provider/model/prompt versions. Writes results to Postgres `eval_runs(run_id, fixture_id, model_snapshot, metrics_json)`.
- **Metrics per event type per fixture:** precision, recall, F1. Plus overall counts (events emitted, false positives, false negatives).
- **Regression signal:** each promotion of a memory record to `global` triggers a re-eval against fixtures that share tags with the record. If recall drops ≥3 points, promotion is blocked and flagged.
- **Human loop:** every correction accepted by a coach is eligible to become a new fixture (builder decides). This is the cheap path to eval growth.

Observability (lightweight; solo dev must afford to read logs):
- Structured logs per stage with `video_id, point_id, window_id` in every line.
- Per-stage timing (ingest, sample, perceive, interpret, memory-retrieve) stored on the job record — directly visible in a "job detail" page.
- Cost tracking: per-VLM-call and per-LLM-call cost estimated from token/frame counts, aggregated per job. "Cost-per-game" is a column on the jobs list from day one.
- Prompt versioning: every `interpret` event stores a `prompt_version` hash; enables "what changed between these two runs".
- No APM tool in v1; Postgres + logs are enough.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Solo + 2–5 alpha coaches | Current stack. Single Postgres, single worker, one object store. Plenty of headroom. |
| 10–50 coaches, ~50 games/week | Scale workers horizontally (same workflow, N processes). Move blob storage from local to S3. Promote pgvector index type (`ivfflat` → `hnsw`). |
| 100+ coaches, ~500 games/week | Split job queue to a dedicated workflow engine (Temporal/Prefect). Consider splitting `perceive` into its own deployment because it's the cost/throughput center. Add Redis for caching hot retrievals. |
| Video archive grows | Move raw-frame artifacts to cold storage after N days; keep only observations + events hot. Videos are not our hosting responsibility. |

### Scaling Priorities

1. **First bottleneck: VLM spend and rate limits.** Address by caching window → observations (idempotent), batching windows per API call where supported, and aggressive sampling-rate tuning. This is architectural, not infrastructural.
2. **Second bottleneck: Postgres for pgvector at growing memory sizes.** Address by promoting index type and partitioning memory by `scope`. Only a real concern past ~500k records.
3. **Third bottleneck: job orchestration.** Home-grown Postgres queue is fine until concurrency exceeds ~20 simultaneous games. Swap to Temporal at that point.

## Anti-Patterns

### Anti-Pattern 1: Coupling Memory Schema to a Specific LLM's Prompt Format

**What people do:** Store memory records as pre-formatted prompt strings for a specific model.
**Why it's wrong:** Next model change invalidates the entire memory store. Defeats the point of external memory.
**Do this instead:** Store structured records (`MemoryRecord` with payload as data). Construct the prompt at interpretation time using a format tailored to the current LLM adapter.

### Anti-Pattern 2: Events Directly Referencing Model Output

**What people do:** Stuff raw VLM JSON into the event row's `details`.
**Why it's wrong:** Swapping models produces incomparable events; UI and exports break.
**Do this instead:** Normalize via `Observation` schema, then produce typed `Event`. Keep raw responses out of the canonical tables (store in object storage, referenced by `raw_response_ref`).

### Anti-Pattern 3: Synchronous Pipeline with Long Timeouts

**What people do:** "Just bump the HTTP timeout to 10 minutes."
**Why it's wrong:** Fragile, bad UX, no partial results, no resume on crash.
**Do this instead:** Async job with progress streaming from the start. It's not much more code, and retrofitting async later is painful.

### Anti-Pattern 4: Rules as Prompt String Only

**What people do:** Paste rules into a system prompt and hope the LLM follows them.
**Why it's wrong:** Rules are enforced statistically, not deterministically. LLM contradictions slip through.
**Do this instead:** Rules as data (YAML) that are both (a) surfaced into the prompt as retrievable rule-memory records and (b) enforced by a deterministic validator that runs after interpretation. Two-layer defense.

### Anti-Pattern 5: Mutating Events in Place on Correction

**What people do:** "UPDATE events SET type='completion' WHERE id=..." when a coach corrects.
**Why it's wrong:** No audit trail; can't re-derive memory; can't diff eval runs against stable events.
**Do this instead:** Immutable events; corrections are their own records; memory promotion reads from corrections. Events can carry `corrected_from_event_id` to chain.

### Anti-Pattern 6: One Worker Processing a Whole Game

**What people do:** A single long-running worker loops through 60 minutes of video.
**Why it's wrong:** Any hiccup loses an hour of work; no parallelism; no partial UI.
**Do this instead:** Fan out per-point; idempotent per-window. Workers are short-lived and interchangeable.

### Anti-Pattern 7: Letting One Coach's Corrections Become Global Memory Immediately

**What people do:** Every correction becomes a global few-shot example.
**Why it's wrong:** Scoring conventions, rule interpretations, and preferences differ across coaches. One coach's "pick" is another's "no-call." Global memory gets polluted.
**Do this instead:** Default correction scope is `coach:<id>`. Promotion to `global` requires multi-coach corroboration or explicit curator action. Eval regression check blocks harmful promotions.

### Anti-Pattern 8: Asking the LLM to Detect Point Boundaries Mid-Stream

**What people do:** Stream continuous events and let the LLM also decide where points start/end.
**Why it's wrong:** Compounds two hard problems; makes reruns expensive; boundaries become entangled with event content.
**Do this instead:** Separate point-detection pass first (cheap, specialized). Per-point processing second. Boundaries editable in UI.

### Anti-Pattern 9: Two Vector Databases

**What people do:** Add a dedicated vector DB "for performance" before there is any scale data.
**Why it's wrong:** Two systems to keep in sync; more ops burden for a solo dev; not needed at alpha scale.
**Do this instead:** pgvector inside Postgres. Migrate only when there is a measured reason.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Managed VLM (Gemini/GPT-4o/Claude video) | `perceive` adapter with provider SDK; structured output / JSON mode | Rate limits and cost are primary constraints. Adapter owns retries + backoff. |
| Managed LLM (Claude/GPT-4) | `interpret` adapter with provider SDK; JSON-mode or tool-use | Prompt version hashed into events. |
| Embedding provider | `memory.embeddings` adapter | Re-embed job if provider changes; memory records unaffected. |
| Self-hosted VLM (Qwen-VL / Llama-Vision via Modal/RunPod) | Same `perceive` adapter interface, different backend | Enabled later if cost or control demands. No other code changes. |
| Object storage (S3 / local in dev) | Pre-signed URL for upload; direct read by workers | Same interface in dev and prod; local dev uses a filesystem-backed S3 emulator. |
| Public video URLs (UFA YouTube, tournaments) | `ingest` can resolve + pull (yt-dlp or equivalent) | Legality to be handled before any public launch (per PROJECT.md). |
| Existing ultimate tools (Penultimate, UltiAnalytics, Hive) | Outbound CSV/JSON export | One-way in v1. No inbound integration. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `perceive` ↔ `interpret` | `Observation` schema (persisted rows, not in-memory) | Model-agnostic. Persistence enables rerun-from-observations without re-paying VLM cost. |
| `interpret` ↔ `memory` | `RetrievalQuery` in, `MemoryRecord[]` out | Memory knows nothing about which LLM is asking. |
| `events` ↔ `api`/`web` | Typed read API; per-point views | UI consumes events, never observations directly. |
| `corrections` ↔ `memory.writer` | Event bus or direct call; idempotent by `correction_id` | Keeps correction ingestion out of the request path. |
| `rulebook/` → `interpret.rules` + `memory.seed` | Rule files are the single source; code + memory both load them | Yearly rule updates → edit YAML → re-seed → one eval re-run. |
| `eval` ↔ everything | Read-only against pinned model versions | Never mutates memory during a run. |

## Sources

- Project context and constraints: `.planning/PROJECT.md` (2026-04-20 snapshot; author-stated pipeline shape, per-point non-negotiable, modularity constraint, solo-build constraint, hybrid hosting posture, staged build plan, 85% recall alpha gate).
- Architectural reasoning derived from the stated constraints; no external architecture references were required for this dimension. STACK and PITFALLS dimensions are expected to verify specific library/infrastructure choices.

---
*Architecture research for: VLM+LLM+external-memory video-to-events pipeline (Ultimate Frisbee)*
*Researched: 2026-04-20*
