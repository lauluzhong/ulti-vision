# Requirements: Sports Video Analytics — Ultimate Frisbee

**Defined:** 2026-04-21
**Core Value:** Turn existing, inconsistent-quality Ultimate Frisbee footage into a reliable per-point event timeline — without requiring the coach to watch the game.

## v1 Requirements

Scope definition: **v1 = what must be true to open alpha to 2–5 friendly coaches.** Anything not required for that milestone is v2.

### Ingest

- [ ] **INGEST-01**: User can upload a local video file (mp4, mov, m4v, webm) via the web UI
- [ ] **INGEST-02**: User can submit a public video URL (YouTube, Vimeo, UFA stream pages) and the system resolves + fetches it
- [ ] **INGEST-03**: System transcodes variable-frame-rate input to constant-frame-rate at ingest (fixes PyAV timestamp drift on iPhone HEVC and similar mobile footage)
- [ ] **INGEST-04**: System normalizes ingested video to a single container/codec/resolution baseline for downstream sampling
- [ ] **INGEST-05**: System persists raw video metadata (duration, source, uploader, upload timestamp) to the primary database

### Points

- [ ] **POINT-01**: System detects point boundaries across a full-game video as a dedicated first pass before per-point processing
- [ ] **POINT-02**: UI exposes a point-boundary editor so coaches can adjust detected boundaries before event processing continues
- [ ] **POINT-03**: Every persisted event carries a `point_id` and an in-point timestamp; every export is sliceable by point

### Perceive (VLM layer)

- [ ] **PERCEIVE-01**: System samples frames from ingested video at a configurable rate (default aligned with Gemini 2.5 Flash native 1fps)
- [ ] **PERCEIVE-02**: VLM adapter emits structured `Observation` records conforming to a versioned schema that is independent of the specific VLM backend
- [ ] **PERCEIVE-03**: Observation outputs are cached keyed on `(video_id, window_id, prompt_version_hash)`; prompt iteration does not re-pay VLM cost for unchanged windows
- [ ] **PERCEIVE-04**: VLM adapter handles rate limits with backoff and records per-call cost + latency

### Interpret (LLM layer)

- [ ] **INTERPRET-01**: LLM adapter consumes Observations plus retrieved memory and emits canonical `Event` records conforming to a versioned schema
- [ ] **INTERPRET-02**: USAU 2024–25 rule set is composed into the LLM prompt at interpretation time and is the single source of rule truth
- [ ] **INTERPRET-03**: LLM structured output is validated against the event schema; schema violations are logged and flagged, never silently dropped

### Memory (external memory / correction loop)

- [ ] **MEMORY-01**: System stores and retrieves rules, few-shot examples (positive + negative), and coach corrections in a model-agnostic schema
- [ ] **MEMORY-02**: Memory retrieval is queryable by event-type tag and by semantic similarity; the retrieval interface is model-agnostic
- [ ] **MEMORY-03**: Coach corrections are ingested into memory with provenance (`coach_id`, `correction_id`, source event, original VLM/LLM output)
- [ ] **MEMORY-04**: Memory promotion gate: a correction only becomes a globally-applied example after corroboration from at least N distinct `coach_id` values OR explicit builder curation. The default N is configurable; during alpha N = 2 plus builder review.
- [ ] **MEMORY-05**: Memory records remain valid across VLM/LLM version changes — swapping either model does not invalidate existing records

### Events (taxonomy & timeline)

- [ ] **EVENT-01**: System emits Goal events with scoring team
- [ ] **EVENT-02**: System emits team-level Possession-change events
- [ ] **EVENT-03**: System emits Completion events (successful passes)
- [ ] **EVENT-04**: System emits Turnover events; classification (drop / throwaway / block / OOB) is best-effort with `"unknown"` as a first-class fallback value
- [ ] **EVENT-05**: System emits pass count per point
- [ ] **EVENT-06**: System emits pass direction (up-field / down-field / lateral / `unknown`); `"unknown"` is the default whenever field orientation is not reliably detectable — the system does not emit confident directions without evidence
- [ ] **EVENT-07**: System emits throw-type classification (forehand / backhand / hammer / blade) as best-effort with `"unknown"` fallback
- [ ] **EVENT-08**: Events are sliceable by point, by event-type, and by team; per-point filtering is a first-class query

### API

- [ ] **API-01**: `POST /ingest` — submit video file or URL; returns job id
- [ ] **API-02**: `GET /jobs/:id` — poll job status with progress stages (ingest → point-detect → per-point perceive → interpret → persist)
- [ ] **API-03**: `GET /games/:id/events` — fetch per-game event timeline, filterable by point / event-type / team
- [ ] **API-04**: `POST /games/:id/corrections` — submit a coach correction against a specific event
- [ ] **API-05**: `GET /exports/:game_id.csv` — download CSV event list (primary export)

### Web UI

- [ ] **UI-01**: Upload page accepts a local file or a public URL; shows progress + estimated time
- [ ] **UI-02**: Game view shows a per-point event list with timestamps that scrub the embedded video to the corresponding moment
- [ ] **UI-03**: Stats dashboard shows, per-game and per-point: completion % (O-line conversion where derivable), turnover count, goals, throw-type mix, pass count
- [ ] **UI-04**: Correction interface supports: flag event as wrong, re-classify event type, mark missed event, delete spurious event — each correction records `coach_id`
- [ ] **UI-05**: Video player hosts the point-boundary editor (POINT-02) as a pre-processing step coaches can run before event extraction finalizes

### Export

- [ ] **EXPORT-01**: CSV export produces one-row-per-event with stable, documented, versioned columns

### Evaluation & Accuracy Gate

- [ ] **EVAL-01**: Human-labeled gold set covers at least 3 full games (~40 points) with independent annotation (not the same person who wrote the prompts)
- [ ] **EVAL-02**: Eval harness computes per-event-type precision and recall against the gold set; reports never macro-average across event types without showing the per-type breakdown
- [ ] **EVAL-03**: Alpha-ready gate: completion recall ≥ 85% with completion precision ≥ 70% on the gold set; goals and possession changes must hit ≥ 95% recall
- [ ] **EVAL-04**: Eval harness runs on every memory promotion as a regression gate — a promotion that degrades the gate metrics is blocked automatically

### Observability

- [ ] **OBS-01**: Per-call and per-game cost is attributed to `video_id`, model, and pipeline stage; aggregate cost per game is recorded
- [ ] **OBS-02**: VLM and LLM call traces (prompt, response, timing, cost, prompt-version-hash) are persisted for debugging and eval replay

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Player identification

- **PLAYER-01**: Jersey OCR for numbered-jersey matching against roster (primary v2 path)
- **PLAYER-02**: Per-team few-shot fine-tune: coach uploads labeled frames once, system does few-shot matching
- **PLAYER-03**: Per-player stats derived from player attribution (completions caught/thrown, Ds, turnovers by player)

### Exports and integrations

- **EXPORT-02**: Excel (.xlsx) export with per-point breakdown sheet and summary stats
- **EXPORT-03**: JSON export (machine-readable, full event schema)
- **EXPORT-04**: One-click push into at least one existing tool (Penultimate / UltiAnalytics / Hive) — pending confirmation an integration pathway actually exists with that tool's authors

### Advanced analytics

- **STATS-01**: O-line conversion % and D-line break % (requires reliable line detection, which depends on goal tracking + point start)
- **STATS-02**: Aggregated patterns across multiple games (season view, opponent view)
- **STATS-03**: Momentum-shift detection
- **STATS-04**: Automatic highlight clip generation (±10s around goals and blocks, per Stanford 2025 MLLM highlight-reel approach)
- **STATS-05**: Field-visualization heatmaps (requires reliable field orientation)

### Perception upgrades

- **PERCEIVE-V2-01**: Adaptive frame sampling (higher rate during action, lower during dead time)
- **PERCEIVE-V2-02**: Deterministic field-line homography module as a supplement to VLM pass-direction inference
- **PERCEIVE-V2-03**: Second-opinion pass with Gemini 2.5 Pro on low-confidence windows

### Hosting / cost

- **HOST-01**: Self-hosted OSS VLM option (Qwen2.5-VL on Modal / RunPod) as an alternative to managed APIs
- **HOST-02**: Batch mode (Gemini batch 50% discount) for non-urgent re-processing runs

### Product surface

- **PROD-01**: Multi-tenant accounts with per-team isolation
- **PROD-02**: Public B2C upload path (anyone can upload)
- **PROD-03**: Near-live / in-game processing
- **PROD-04**: Generalization to other sports

## Out of Scope

Explicitly excluded from both v1 and the current v2 plan. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Player facial identification | Amateur Ultimate footage is multi-angle, obstructed, variable lighting. Face recognition is error-prone and the risk/reward is poor. See PROJECT.md Key Decisions. Roster + jersey OCR is the v2 path instead. |
| Chip / GPS player tracking | Requires hardware buy-in and kills the "extract from existing footage" core thesis. |
| Custom-trained VLM from scratch | Thesis: frontier VLMs + external memory + LLM interpretation generalize better than bespoke models. Revisit only if this hypothesis fails on the gold set. |
| Tournament management, team management, rosters/scheduling | Existing products (Penultimate, UltiAnalytics, Hive) already do this. Stay focused on extraction. |
| Native video hosting (long-term storage for user uploads) | Not a video platform. Short-term working storage only, per PROJECT.md. |
| Coaching recommendations / auto-generated "scouting reports" | Product shows coaches what happened; does not tell them what to do. Coach-generated insight is the value, not AI-generated opinion. |
| Stall-count / stall-out detection | Requires audio detection of a called stall. Visual signal is unreliable. Emit `turnover: unknown` as the safe fallback. |
| Foul / travel / pick detection | Contested verbal calls with no clean visual signal. High false-positive risk with low coach value. |
| In-game / near-live processing | v1 is post-game only. End-state possibility, not a v1 feature. |
| Non-Ultimate sports | Ultimate is the hard case. Generalization comes after it works. |

## Traceability

Which phases cover which requirements. Updated by the roadmapper during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INGEST-01 | TBD | Pending |
| INGEST-02 | TBD | Pending |
| INGEST-03 | TBD | Pending |
| INGEST-04 | TBD | Pending |
| INGEST-05 | TBD | Pending |
| POINT-01 | TBD | Pending |
| POINT-02 | TBD | Pending |
| POINT-03 | TBD | Pending |
| PERCEIVE-01 | TBD | Pending |
| PERCEIVE-02 | TBD | Pending |
| PERCEIVE-03 | TBD | Pending |
| PERCEIVE-04 | TBD | Pending |
| INTERPRET-01 | TBD | Pending |
| INTERPRET-02 | TBD | Pending |
| INTERPRET-03 | TBD | Pending |
| MEMORY-01 | TBD | Pending |
| MEMORY-02 | TBD | Pending |
| MEMORY-03 | TBD | Pending |
| MEMORY-04 | TBD | Pending |
| MEMORY-05 | TBD | Pending |
| EVENT-01 | TBD | Pending |
| EVENT-02 | TBD | Pending |
| EVENT-03 | TBD | Pending |
| EVENT-04 | TBD | Pending |
| EVENT-05 | TBD | Pending |
| EVENT-06 | TBD | Pending |
| EVENT-07 | TBD | Pending |
| EVENT-08 | TBD | Pending |
| API-01 | TBD | Pending |
| API-02 | TBD | Pending |
| API-03 | TBD | Pending |
| API-04 | TBD | Pending |
| API-05 | TBD | Pending |
| UI-01 | TBD | Pending |
| UI-02 | TBD | Pending |
| UI-03 | TBD | Pending |
| UI-04 | TBD | Pending |
| UI-05 | TBD | Pending |
| EXPORT-01 | TBD | Pending |
| EVAL-01 | TBD | Pending |
| EVAL-02 | TBD | Pending |
| EVAL-03 | TBD | Pending |
| EVAL-04 | TBD | Pending |
| OBS-01 | TBD | Pending |
| OBS-02 | TBD | Pending |

**Coverage:**
- v1 requirements: 45 total
- Mapped to phases: 0 (pending roadmap)
- Unmapped: 45 ⚠️ (will be resolved by roadmapper)

---
*Requirements defined: 2026-04-21*
*Last updated: 2026-04-21 after initial definition*
