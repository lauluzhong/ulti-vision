# Project Research Summary

**Project:** Ultimate Frisbee Video Analytics — VLM+LLM+Memory Event Extraction Pipeline
**Domain:** Sports video-to-events ML pipeline; B2C coaching analytics SaaS
**Researched:** 2026-04-20
**Confidence:** HIGH on stack pricing and event taxonomy; MEDIUM on retrieval heuristics and pass-direction approach; LOW on self-host cost projections

---

## Executive Summary

This product is a two-stage ML pipeline that converts raw Ultimate Frisbee footage into structured, per-point event timelines without any human sideline operator. The VLM layer (Gemini 2.5 Flash) ingests video natively and emits structured observations; the LLM layer (Claude Sonnet 4.5) reconciles those observations against USAU rules and retrieved few-shot examples to produce canonical events. An external memory store accumulates corrections and positive/negative examples so the system compounds in accuracy over time. No competitor does this — every existing tool (Penultimate, Statto, UltiAnalytics) requires a human at the sideline keying events in real time. This is the first video-extraction layer for the sport.

The recommended architecture is a five-package pipeline (ingest → sampler → perceive → interpret → events) with an orthogonal memory package that both sides of the pipeline write to and read from. Three adapter boundaries — perceive, interpret, and embeddings — make every AI component swappable without touching the memory store or event schema. The entire state lives in one Postgres instance (with pgvector) and one object store (Cloudflare R2). A Dramatiq+Redis job queue handles the async processing that 60-minute games require. The frontend is minimal: SvelteKit upload/review/correct UI backed by FastAPI. The build sequence ends at a closed alpha of 2–5 coaches; the memory architecture must be production-ready before that alpha opens because coach corrections compound into the memory store from day one.

The primary risk bundle is around accuracy on amateur footage: disc invisibility, similar-color kits, variable-framerate mobile video, and VLM temporal confusion collectively threaten the 85% recall alpha gate before it is ever measured against a real eval set. The second risk is cost discipline — Gemini re-uploads and lack of per-window observation caching can produce 3–10x cost spikes during prompt iteration. Both risk bundles must be addressed in the ingest and perception design phases, not retrofitted. Pass direction is the single feature where the VLM thesis is weakest: ICCV 2025 research shows VLMs score ~50–60% on spatial orientation tasks, meaning the system should default pass_direction: unknown unless field lines are visible, and optionally use a lightweight deterministic homography approach as a supplement.

---

## Top Decisions and Takeaways That Affect v1 Scope and Phase Structure

These are the seven findings that directly gate phase structure, feature priority, or architectural commitment.

**1. Per-point decomposition is non-negotiable and drives the entire pipeline shape.**
Every event, stat, and export must be sliceable by point. This is not a UI feature — it is an architectural constraint. Point detection must run as a dedicated first pass before per-point processing begins. If point boundaries are wrong, every downstream event is misattributed. The point-boundary editor must exist in the UI before coaches see any results. This makes "point detection" a phase gate, not a feature.

**2. The memory architecture must be alpha-ready before coaches arrive.**
Coach corrections flow into external memory from the first alpha interaction. If the memory writer, correction scoping, and promotion logic are not working correctly when the first coach submits a correction, those corrections are either lost or cause silent overfitting. The memory loop is not a v2 feature — it is a pre-alpha deliverable.

**3. Pass direction is the VLM thesis's weakest point — do not ship it as a reliable stat.**
FEATURES.md lists pass direction as a P1 differentiator. PITFALLS.md (Pitfall 5) directly contradicts its reliability: VLMs score ~50–60% on spatial orientation from non-broadcast footage, the same as chance for a binary upfield/downfield call. The roadmap must make a clear decision: ship pass direction with a prominent "unknown" fallback for amateur footage (the honest path), optionally supplement with a YOLO-based field-line homography for clips where lines are visible (the accurate path), but never emit confident directional labels when field orientation cannot be determined. Pass direction should appear in the schema and export from day one but be documented as best-effort with a high "unknown" rate for amateur footage.

**4. VFR transcoding is an ingest-phase gate, not a later hardening step.**
iPhone HEVC/H.265 footage with variable frame rate causes PyAV to report time_base=0/0, producing timestamps that are off by 30–120 seconds on a 60-minute game. This is the most common footage type for club Ultimate. A single ffmpeg CFR transcode step in ingest fixes it. If this step is missing, every timestamp in every event is wrong for the majority of footage sources. This must ship in the ingest phase, and CI must include at least one iPhone HEVC fixture.

**5. Per-window observation caching is a cost gate that must ship in Phase 1.**
Without caching the Observation[] output from each VLM call keyed on (video_id, window_id, prompt_version_hash), every prompt iteration re-invokes Gemini at full cost. A 60-minute game re-run three times during prompt tuning costs 3x $0.40–$1.60 per iteration. At alpha scale with 10 games under active iteration, this adds up fast. The caching pattern is a day-one requirement (per PITFALLS.md Technical Debt table) and gates any serious prompt iteration workflow.

**6. Eval harness must be built before any accuracy claims, with per-event-type metrics.**
PITFALLS.md (Pitfall 8) documents how macro-averaged recall inflates metrics by hiding low recall on common events (completions) behind high recall on rare events (goals). The alpha gate is ~85% completion recall (the highest-frequency event type) with a co-equal precision floor (~70%). The gold set must span at least 3 full games (~40 points), independently annotated. The eval harness must report per-event-type precision and recall separately and must run on every memory promotion as a regression gate. This is a build-before-alpha-open deliverable.

**7. Correction scoping requires hard enforcement of the multi-coach corroboration gate.**
During alpha, if only one coach is active, "N distinct coaches corroborate" degrades to "same coach confirms 3 times." Any memory record promoted to scope: global via a single coach's confirmations will encode that coach's personal conventions as universal rules. Hard enforcement: promotion to global requires 2+ distinct coach_id values. During early alpha with 1–2 coaches, no record should reach global scope without manual curator review. This must be enforced in code, not just policy.

---

## Key Findings

### Recommended Stack

The stack is deliberately conservative for a solo build: one language (Python 3.12), one database (Postgres + pgvector), one object store (Cloudflare R2), and thin adapter layers wherever an AI provider might be swapped. Gemini 2.5 Flash is the only viable VLM choice because it is the only frontier model with native video input, billing video at ~$0.40/game vs. ~$7–$29/game for GPT-4o or Claude with manual frame extraction. Claude Sonnet 4.5 is the LLM for interpretation because of its superior structured-output compliance and 1M-context + 0.1x prompt-cache pricing ($1.56/game cached). The two-vendor split (Gemini for perception, Claude for interpretation) is worth it for accuracy and cost; a single-vendor Gemini 2.5 Pro stack is a valid simplification if vendor count matters more than last-10% accuracy.

The job queue is Dramatiq + Redis, not FastAPI BackgroundTasks (which would starve request handlers on a 10-minute job). Observability is Langfuse Cloud from day one — cost-per-game is a required column on the jobs list. Pydantic AI provides thin provider-swap plumbing without hiding prompts. LangChain is explicitly excluded because hiding prompts is fatal to a project where "external memory = explicit prompt engineering that compounds."

**Core technologies:**
- **Gemini 2.5 Flash** (VLM/perception): native video input, ~$0.40/game, no client-side frame extraction
- **Gemini 2.5 Pro** (VLM/fallback): hard-clip reprocessing, ~$1.60/game, route based on Flash confidence score
- **Claude Sonnet 4.5** (LLM/interpretation): best-in-class structured output, 1M context, 0.1x cache reads
- **Pydantic AI** (orchestration): thin provider-swap layer, keeps prompts inspectable
- **Postgres + pgvector** (persistence): events, memory, corrections, embeddings — one system
- **LanceDB** (semantic retrieval): embedded, zero-ops, handles example bank at alpha scale
- **PyAV + ffmpeg** (video): frame extraction, CFR transcoding, clip slicing
- **Dramatiq + Redis** (job queue): async per-point fan-out, resume on crash
- **FastAPI** (API): upload, job status, events, corrections, exports
- **SvelteKit 2** (frontend): upload, per-point event list, correction interface, video deep-link
- **Cloudflare R2** (blob): zero egress, 7-day lifecycle on raw video
- **Langfuse Cloud** (observability): per-game cost tracking, trace per VLM/LLM call
- **Fly.io** (hosting): API + worker, persistent volumes for Postgres/LanceDB

### Expected Features

No existing tool does video-to-events extraction. Every feature that requires a human sideline operator today becomes a differentiator here. The critical dependency chain is: point detection → per-point event timeline → all stats and exports. O/D line labeling requires reliable goal detection (a chicken-and-egg risk). Pass direction requires field orientation, which requires either a visible scoreboard or pull-direction inference.

**Must have (table stakes) — alpha launch:**
- Video ingest: file upload + YouTube URL paste with ToS acknowledgment
- Async job processing with per-point progress streaming (not a spinner)
- Per-point event timeline: pull, completion, turnover, goal, possession_start, point_end
- Timestamp deep-link: click event → seek video to that moment (primary trust-builder)
- O/D line labeling per point (hold / break / unknown)
- Stats dashboard: completion %, turnover count, O-line conversion %, D-line break %, pass count
- Event correction: flag as wrong + re-classify event type → feeds memory
- CSV export with human-readable columns only (internal IDs in JSON export only)
- ~85% completion/turnover/goal recall at 70%+ precision (alpha gate)

**Should have (differentiators) — alpha launch, degradable:**
- Turnover sub-classification: throwaway, drop, block, OOB (emit "unknown" when uncertain)
- Throw type: backhand, forehand, hammer (emit null when uncertain)
- Pass direction: upfield, lateral, downfield (emit "unknown" when field orientation not determinable — expected to be the dominant value for amateur footage)
- Correction-fed memory improvement (visible to coaches as "you've made N corrections")

**Defer (v1.x, after first correction cycle):**
- Multi-game aggregated stats dashboard
- Highlight clip auto-generation (ffmpeg ± 10s around event timestamp)
- Point-boundary editor with full UI (flag-and-correct flow is v1; drag-handle editor is v1.x)
- Momentum detection (scoring runs, consecutive breaks)

**Defer (v2+):**
- Player identification (jersey OCR, few-shot fine-tune per team)
- Per-player stats: completion %, turnovers, assists, +/-
- Near-live / in-game processing (fundamentally different architecture)
- Expected goals / field value model (requires coordinate data)

### Architecture Approach

The pipeline separates into five sequential stages with one orthogonal memory package. Point detection runs as a dedicated first pass; all per-point processing is then parallelized across 12–20 points per game using asyncio.gather, each point getting its own sample → perceive → interpret fan-out. Observations are persisted between perceive and interpret, making prompt-only re-runs free (no Gemini re-call). Events are immutable; corrections are first-class records that trigger memory writer promotion rather than in-place mutations. Every adapter boundary (VLM, LLM, embeddings) satisfies a Protocol interface so provider swaps touch one file.

**Major components:**
1. **`ingest`** — normalize codec (CFR transcode for VFR), probe metadata, store blob to R2, write videos row
2. **`sampler`** — extract per-point windows at ~3 fps fixed; window idempotency keyed on (video_id, start_ms, end_ms, fps)
3. **`perceive`** — VLM adapter (Gemini primary); Observation[] persisted to DB; re-run is free if window observations exist
4. **`interpret`** — LLM adapter (Claude primary) + USAU rule validator; retrieves 4–8 memory records per event candidate; produces Event[] with memory_refs and rule_refs
5. **`memory`** — tag+vector retrieval; writer promotes corrections to few_shot_positive/negative records; scope-gated to prevent cross-coach contamination
6. **`events`** — timeline store; per-point views; CSV/JSON export
7. **`api`** — FastAPI thin HTTP surface; enqueues jobs, streams SSE status, serves corrections
8. **`eval`** — gold-set fixtures + regression harness; runs on every memory promotion; blocks global promotion if recall drops ≥3 points

### Critical Pitfalls

1. **VFR timestamp corruption (Pitfall 10)** — iPhone HEVC footage gives time_base=0/0 in PyAV, producing timestamps off by 30–120 seconds. Prevention: always CFR-transcode in the ingest step before any frame extraction. Gate: CI must include one iPhone HEVC fixture before calling ingest "done."

2. **Gemini re-upload cost spiral (Pitfall 6)** — without caching file_uri and Observation[] output per window, every prompt iteration re-pays full VLM cost. Prevention: store file_uri + expiry_time in DB, check before re-uploading; cache observations keyed on (video_id, window_id, prompt_version_hash). Gate: zero duplicate Gemini calls for the same window in Langfuse.

3. **Pass direction false confidence (Pitfall 5)** — VLMs score ~50–60% on spatial orientation (same as chance for binary upfield/downfield). Prevention: default pass_direction: unknown; only emit a direction when scene.field_visible == "full" AND field orientation is determinable. Never emit confident direction labels for zoomed-in or handheld footage.

4. **Memory scope collapse (Pitfall 7)** — one eager coach's corrections can become global memory if the corroboration gate is weak. Prevention: hard-enforce 2+ distinct coach_id values for scope: global promotion; during alpha, all global promotions require curator review.

5. **Eval metric gaming (Pitfall 8)** — macro-averaged recall hides low completion recall behind perfect goal recall. Prevention: report per-event-type precision and recall separately; use instance-weighted (micro) recall as the primary alpha gate; set a co-equal precision floor of ~70%. Gold set minimum: 3 full games, independently annotated.

6. **LLM confabulation on sparse observations (Pitfall 11)** — Claude emits events when observations only show state, not action. Prevention: system prompt must require at least one actions_detected entry to emit an event; post-interpretation validator flags events with no corroborating action.

7. **Possession team oscillation on similar-color kits (Pitfall 4)** — lighting changes flip team labels across windows. Prevention: inject a "color contract" (team A = dark jerseys) into every clip prompt; validate in the rule-validator that possession cannot switch teams without an explicit action event.

---

## Implications for Roadmap

### Phase 1: Foundation and Ingest

**Rationale:** Nothing works without reliable ingest and a functioning data contract. VFR transcoding must land here or every timestamp in every phase is wrong. Observation caching must land here or every subsequent phase iteration is expensive. The data schemas (Observation, Event, MemoryRecord) are the hard interfaces that every other phase builds against.

**Delivers:**
- Postgres schema: videos, windows, observations, events, memory, corrections, jobs
- Pydantic models: Observation, Event, MemoryRecord (swap-safe contracts)
- Video ingest: file upload + YouTube URL, CFR transcode for VFR footage, R2 blob storage
- Frame sampler: fixed 3fps, window construction, per-window idempotency keys
- Per-window observation caching: skip Gemini if cache hit on (video_id, window_id, prompt_version_hash)
- Langfuse instrumentation: per-call cost tracking, game_id tagging
- Jobs list with cost-per-game column (day-one requirement)

**Addresses:** VFR timestamp corruption (Pitfall 10), Gemini re-upload cost (Pitfall 6), swap-safety contract definition
**Must avoid:** Using FastAPI BackgroundTasks for video jobs; storing raw VLM output as the observation record

**Research flag:** Standard patterns — no deeper research needed.

---

### Phase 2: Perception and Interpretation (Single-Game Pipeline, CLI-Only)

**Rationale:** Prove the VLM→LLM pipeline end-to-end on one short clip before building any UI or queue. Memory retrieval starts as a stub returning [] (rules-only prompt). This validates the core hypothesis and catches VLM temporal confusion, disc invisibility, and confabulation problems in a controlled setting before they affect alpha coaches.

**Delivers:**
- Gemini 2.5 Flash adapter (perceive) with Observation structured output
- USAU rule validator (deterministic post-interpretation layer)
- Claude Sonnet 4.5 adapter (interpret) with rules-only prompt (no memory retrieval yet)
- Closed event enum: completion, turnover, goal, possession_start, point_end, unknown
- CLI entrypoint: gsd perceive <window_id>, gsd interpret <point_id>
- Point detection: scoreboard OCR + pull-detection heuristic (cheap first pass)
- Prompt: explicit instruction to emit only events supported by actions_detected; disc.visibility_quality field; inferred: bool flag for cross-window state-change inferences

**Addresses:** VLM temporal confusion (Pitfall 1), disc invisibility vs. absence (Pitfall 2), LLM confabulation (Pitfall 11)
**Tension resolved:** Pass direction — ship field with "unknown" as the dominant value; no confident directional inference until field-line heuristic is validated in a later phase.

**Research flag:** VLM prompt design for structured Ultimate observations from amateur video warrants a focused research sub-session before writing the perceive prompt.

---

### Phase 3: Memory Foundation and Correction Loop

**Rationale:** This is the pre-alpha architectural gate. Memory must be operational before coaches see the product because their first corrections must compound correctly. Rushing this phase and opening alpha prematurely produces garbage memory that is expensive to clean up.

**Delivers:**
- Memory package: SQLite (source of truth) + LanceDB (semantic retrieval)
- Seed memory: ~20–30 hand-crafted few-shot records for the four MVP event types, USAU rules as kind=rule records
- Memory retrieval integrated into interpret: 4–8 records per candidate, tag-filter first, vector-rank second, diversity cap
- Memory writer: correction → positive/negative MemoryRecord pair, scope: coach:<id> default
- Correction API: POST /corrections → immutable corrections table → memory writer → re-embed
- Scope enforcement: hard gate — scope: global requires 2+ distinct coach_id values; alpha = curator review before any global promotion
- memory_refs required (not nullable) on every Event row — non-negotiable audit trail

**Addresses:** Memory scope collapse (Pitfall 7), correction loop non-reproducibility (Pitfall 9)
**Must avoid:** scope: global as default; mutating memory records in place; promoting without eval regression check

**Research flag:** Retrieval budget (4–8 records) and corroboration threshold (K=2) need empirical calibration against the gold set.

---

### Phase 4: Async Orchestration and API

**Rationale:** The CLI pipeline from Phases 2–3 becomes a durable async job. Partial results stream per-point so coaches see early points while later ones are processing. Resume-on-crash means a worker restart does not re-invoice Gemini for completed windows.

**Delivers:**
- Dramatiq + Redis job queue replacing CLI sync execution
- process_game workflow: ingest → detect_points → fan-out per-point → persist → notify
- Per-window idempotency enforced: worker checks window.status before calling Gemini
- SSE or polling endpoint for job status with per-point progress
- FastAPI routes: POST /ingest, GET /jobs/:id, GET /games/:id/events, POST /corrections, GET /exports/:id
- Cloudflare R2 signed-upload path for large files
- Per-point partial results available in DB before game fully completes

**Addresses:** Anti-pattern 3 (synchronous pipeline), Anti-pattern 6 (whole-game single worker)
**Research flag:** Standard patterns — Dramatiq async actors are well-documented.

---

### Phase 5: Eval Harness and Alpha Gate

**Rationale:** No accuracy claims before this phase. The eval harness is the instrument that determines whether the product is ready for coaches. It must be built before alpha opens, not after.

**Delivers:**
- Gold set: 3 full games (~40 points), human-labeled by builder + at least 1 trusted coach, inter-annotator agreement measured
- eval/harness.py: runs pipeline against gold fixtures with pinned model + prompt versions
- Per-event-type precision and recall (completions, turnovers, goals separately — never a single aggregate)
- Alpha gate check: instance-weighted recall ≥85% on completions + turnovers, precision ≥70% on completions
- Memory promotion regression gate: re-runs harness before every scope: global promotion, blocks if any event type drops ≥3 points recall
- eval_runs table in Postgres: run_id, fixture_id, model_snapshot, prompt_version_hash, metrics JSON

**Addresses:** Eval metric gaming (Pitfall 8); binary gate for proceeding to Phase 6

**Research flag:** Standard patterns for eval pipeline code. The hard work is annotation effort: plan 8–15 hours for gold set labeling.

---

### Phase 6: Minimal Web UI and Alpha Launch

**Rationale:** With pipeline, memory, async orchestration, and passing eval, the product is ready for 2–5 friendly coaches. The UI must deliver the first-upload experience in under 5 minutes.

**Delivers:**
- SvelteKit upload form + job status page (SSE polling)
- Per-point event list: grouped by point ordinal, event rows with click-to-seek video timestamp
- Stats dashboard: completion %, O-line conversion %, D-line break %, pass count, turnover count
- Correction interface: click event → select correct type → save (three interactions max)
- Team color contract UI: show inferred team descriptors before processing, let coach correct in 5 seconds
- CSV export with human-readable columns only (no internal IDs)
- Confidence displayed as traffic-light (green/yellow/red), not raw 0.0–1.0
- Alpha documentation: explicit statement that pass direction has high "unknown" rate for amateur footage; sub-second events (quick drops) may be missed

**Addresses:** All UX pitfalls (PITFALLS.md UX section), possession team confusion (Pitfall 4), coach trust via timestamp deep-link

**Research flag:** SvelteKit + tanstack/table patterns are standard. Video timeline (video.js or native seek) may need a quick implementation research pass.

---

### Phase 7: Hardening and v1.x Features

**Rationale:** After first correction cycle produces meaningful memory records, add features that depend on multi-game data or validated memory quality.

**Delivers:**
- Multi-game aggregated stats (schema ready from Phase 1; UI is new)
- Highlight clip auto-generation: ffmpeg ± 10s around event timestamp for all goals, all blocks
- Point-boundary editor with full drag-handle UI
- Adaptive sampling: frame-diff magnitude trigger bumps 3fps → 5fps for 2 seconds around motion spikes
- Second VLM adapter (self-hosted Qwen2.5-VL on Modal) — proves swap-safety under actual swap
- Cost dashboard: trend line of cost-per-game over time

**Research flag:** Modal GPU provisioning for Qwen2.5-VL self-hosting needs a research sub-session when cost pressure warrants it.

---

### Phase Ordering Rationale

- **Ingest before perception:** VFR transcoding and observation caching are pre-conditions for everything. Wrong timestamps corrupt every downstream phase.
- **CLI pipeline before async orchestration:** Proves the hypothesis cheaply before adding infrastructure complexity. A working CLI pipeline is also the test harness for the async workflow.
- **Memory before alpha:** Coach corrections from the first interaction must compound correctly. A half-built memory loop opened to alpha coaches produces garbage that is expensive to clean.
- **Eval before UI:** The eval harness determines whether the product should be shown to coaches at all. Building UI before passing eval wastes coach trust.
- **UI designed for trust, not completeness:** The first-upload experience (per-point grouping, timestamp deep-link, one meaningful stat) is the trust mechanism. Every UX pitfall that erodes trust must be addressed before a single coach uploads.

---

### Research Flags

**Phases needing deeper research during planning:**
- **Phase 2 (VLM prompt design):** Structured observation extraction from sports video using Gemini is a sparse domain. A focused research session on VLM prompt strategies for temporal event detection in non-broadcast footage is warranted before writing the perceive prompt. Observation schema design (especially disc.visibility_quality, scene.multiple_discs_possible, and action-confidence fields) may benefit from sports-video ML observation ontologies.
- **Phase 3 (retrieval calibration):** The 4–8 record retrieval budget and K=2 corroboration threshold need empirical tuning against the gold set. Plan for a calibration sub-phase within Phase 3.
- **Phase 7 (self-hosted VLM):** Modal pricing for Qwen2.5-VL at alpha scale and quantization options (7B vs. 72B) need verification when cost pressure triggers the switch.

**Phases with standard patterns (skip additional research):**
- **Phase 1 (ingest/schema):** PyAV + ffmpeg + Postgres schema + R2 signed upload are well-documented.
- **Phase 4 (async orchestration):** Dramatiq + Redis patterns are well-documented.
- **Phase 5 (eval harness):** Standard ML eval pipeline; the hard work is annotation, not code.
- **Phase 6 (SvelteKit UI):** Component patterns with shadcn-svelte and tanstack/table are well-documented.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Pricing verified against official docs 2026-04-20. Gemini native video cost advantage is decisive. Pydantic AI is pre-1.0 — API may churn; migration to raw SDKs is trivial. |
| Features | HIGH | Event taxonomy cross-referenced against USAU rulebook, UFA Glossary, UltiAnalytics, Statto. Integration surfaces (CSV field names) are MEDIUM — no public API spec for Penultimate. |
| Architecture | HIGH | Derived directly from PROJECT.md constraints. Specific retrieval budget numbers (4–8 records) need empirical validation. |
| Pitfalls | HIGH on VFR, disc invisibility, and cost traps (verified sources). MEDIUM on memory architecture pitfalls (RAG production failure literature). MEDIUM on pass direction (ICCV 2025 VLM4D). |

**Overall confidence:** HIGH on build approach and architecture; MEDIUM on the specific accuracy numbers that will emerge from the gold set eval.

### Gaps to Address

- **Pass direction accuracy in practice:** The decision to default to "unknown" is correct. Open question: whether a lightweight field-line homography module is worth building in Phase 2 or deferring to Phase 7. Recommendation: defer; ship "unknown" dominant in Phase 2; revisit after alpha coaches report how much they care about directional stats.

- **Point detection reliability on no-scoreboard footage:** Point boundary detection via scoreboard OCR fails on handheld footage with no overlay. The fallback (pull-detection heuristic + VLM Q&A at 1fps) needs empirical validation. The point-boundary editor is the escape valve.

- **Gold set annotation effort:** Labeling 3 full games (~40 points) requires 8–15 hours of careful human annotation. This is not a code gap but a time investment that must be planned explicitly in the roadmap.

- **Inter-coach calibration on correction semantics:** When 2–5 coaches submit corrections, their interpretations of USAU rules will differ. The USAU rule surfacing in the correction UI is the right mitigation, but a short onboarding rules walk-through for alpha coaches may be needed to align expectations.

---

## Sources

### Primary (HIGH confidence)
- `.planning/PROJECT.md` — scope, constraints, non-negotiables, staged timeline
- `.planning/research/STACK.md` — official pricing docs for Gemini, Claude, Modal, R2 verified 2026-04-20
- `.planning/research/FEATURES.md` — USAU rulebook, WFDF rules, UFA Glossary, UltiAnalytics, Statto
- `.planning/research/PITFALLS.md` — VidHalluc (CVPR 2025), VLM4D (ICCV 2025), Stanford CS231N Ultimate disc tracking, PyAV VFR issue, OWASP LLM01:2025

### Secondary (MEDIUM confidence)
- `.planning/research/ARCHITECTURE.md` — component design derived from PROJECT.md constraints
- dfiorino/ultianalyticspull README — UltiAnalytics column structure (inferred, not official schema)
- FiveThirtyEight Ultimate analytics article — coach data needs (undated, core thesis stable)
- BentoML 2026 open-source VLM guide — Qwen2.5-VL vs. Llama Vision / Pixtral positioning

### Tertiary (LOW confidence, needs validation)
- Modal "3x production tier multiplier" — found in one secondary source; verify in Modal billing docs before any scale-up plan
- yt-dlp legal status for dev use — grey area; the production mitigation (require user-uploaded footage) is the correct answer regardless

---

*Research completed: 2026-04-20*
*Ready for roadmap: yes*
