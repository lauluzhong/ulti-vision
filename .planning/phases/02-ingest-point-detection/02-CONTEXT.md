# Phase 2: Ingest & Point Detection - Context

**Gathered:** 2026-04-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 2 turns the Phase 1 local-clip vertical slice into a real full-game ingest boundary. It accepts local video files and approved public URLs, normalizes them into the project's ingest baseline, detects point boundaries before any downstream perception runs, and establishes stable point identifiers so every later event is sliceable by point.

</domain>

<decisions>
## Implementation Decisions

### URL ingest architecture
- **D-01:** v1 URL ingest is explicitly allowlisted to YouTube and UFA stream pages only. Other URLs return a 400-style validation failure instead of falling through to generic `yt-dlp` behavior.
- **D-02:** URL ingest requires an explicit rights acknowledgment on every call. CLI uses `--ack-rights` now; the future HTTP surface carries the equivalent boolean field without changing the decision.
- **D-03:** Rights acknowledgment logging stores URL, ISO timestamp, and caller identifier in a dedicated `rights_acks` table. CLI uses a caller-supplied identity now; Phase 7 can map this to `coach_id`.
- **D-04:** If `yt-dlp` cannot fetch a URL anonymously, Phase 2 fails loudly with a clear public-URLs-only error. No cookies flow, auth bypass, or private-video support enters v1.

### Point-boundary detection fusion
- **D-05:** Point detection is a dedicated pre-perception stage inserted between ingest normalization and per-window perception. No downstream window processing begins until boundaries exist.
- **D-06:** Boundary detection uses a staged fusion strategy: scoreboard OCR is the primary signal, pull/start-of-play heuristics are the secondary signal, and cheap VLM Q&A is only used to disambiguate candidate spans instead of scanning the entire game.
- **D-07:** The detector persists boundary evidence per point candidate, including which signals fired and a confidence score, so later phases and the eventual UI editor can inspect why a boundary was chosen.
- **D-08:** Phase 2 should prefer honest partial success over false certainty. If a boundary is uncertain, the system still emits a best-effort point segment with low-confidence evidence rather than fabricating a precise transition.

### Upload + API surface
- **D-09:** Phase 2 ships the ingest capability as a backend-first service with thin invocation surfaces, not a coach-facing UI. The canonical surface is a synchronous local/API ingest entrypoint that accepts file upload or approved URL and returns normalized ingest metadata plus detected point boundaries.
- **D-10:** Local file support remains broad for `mp4`, `mov`, `m4v`, and `webm`. The same normalization path handles both file and URL sources so there is one ingest baseline, not two divergent codepaths.
- **D-11:** The Phase 2 HTTP surface stays intentionally thin: submit file or URL, require rights ack for URLs, return the normalized video/blob metadata and point-boundary output. Durable jobs, polling, and partial-result streaming remain Phase 6 work.
- **D-12:** CLI parity is maintained in Phase 2 so the builder can exercise ingest and point detection without going through the HTTP layer. CLI and API must call shared service code rather than duplicating ingest logic.

### Point ID semantics
- **D-13:** Phase 2 introduces a first-class point record rather than treating `point_id` as an ad hoc string on events only. Point boundaries need their own persisted rows so later correction and rebucketing work cleanly.
- **D-14:** `point_id` is an opaque, stable per-game identifier derived from point order, not from raw timestamps. Timestamp edits should update point boundaries without forcing downstream ids to be renamed.
- **D-15:** Events keep their absolute `video_ts_ms` and also gain an explicit in-point timestamp field derived from the enclosing point's start offset. This is a contract requirement for downstream exports and per-point queries, not a UI-only concern.
- **D-16:** Downstream phases inherit point assignment from Phase 2 rather than recomputing it. The point detector is the single source of truth for point membership.

### the agent's Discretion
- Exact confidence threshold tuning for OCR / heuristic / VLM fusion
- Internal naming of the synchronous Phase 2 HTTP route(s), as long as the surface stays thin and Phase 6 can supersede it cleanly
- Exact storage shape for boundary evidence payloads, as long as it is persisted and queryable

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and success criteria
- `.planning/ROADMAP.md` — Phase 2 goal, dependencies, and success criteria
- `.planning/REQUIREMENTS.md` — INGEST-01, INGEST-02, POINT-01, POINT-03 definitions and traceability
- `.planning/PROJECT.md` — core value, per-point non-negotiable constraint, and ingest/cost posture

### Research constraints
- `.planning/research/SUMMARY.md` — phase-shaping findings on point detection, ingest risk, and cost discipline
- `.planning/research/ARCHITECTURE.md` — pipeline boundaries, package layout, and point/event data flow expectations
- `.planning/research/PITFALLS.md` — ingest and temporal-failure modes to avoid while planning Phase 2

### Prior phase carry-forward
- `.planning/phases/01-foundation-narrow-vertical-slice/01-VERIFICATION.md` — what Phase 1 proved and what Phase 2 must preserve
- `.planning/phases/01-foundation-narrow-vertical-slice/01-05-SUMMARY.md` — where point detection inserts into the existing pipeline assembly point

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/sva/ingest/ingest.py`: already probes metadata, transcodes to CFR, persists a `jobs` row, and computes ingest windows for local files
- `src/sva/cli.py`: existing Typer CLI is the natural place to extend local-vs-URL ingest parity and rights-ack flags
- `src/sva/pipeline.py`: current assembly point where the Phase 2 point-detection stage should sit between ingest and per-window perception
- `src/sva/models.py`: `Event.point_id` and `point_ordinal` already exist as placeholders, which makes the Phase 2 contract evolution straightforward
- `src/sva/events_dao.py`: current event persistence path is the place where non-null point assignment will start mattering

### Established Patterns
- Phase 1 kept CLI and orchestration thin while core behavior lives in service modules under `sva.*`
- Data contracts are versioned, swap-safe Pydantic models; downstream changes should preserve that shape-first discipline
- Database persistence is introduced through migrations plus small ORM/DAO layers rather than raw scattered SQL

### Integration Points
- Insert point detection into `run_pipeline()` after `ingest_clip()` and before the per-window perception loop
- Extend `sva.ingest` with URL resolution, rights-ack logging, and normalized-source handling without duplicating local-file ingest logic
- Add point persistence and point lookup alongside the existing `jobs` / `events` schema so later phases can assign events by persisted point rows

</code_context>

<specifics>
## Specific Ideas

- Cheap VLM should act as a tie-breaker on ambiguous spans, not as a whole-game primary detector
- Phase 2 should keep one normalization pipeline for file and URL sources
- The Phase 2 API surface should be intentionally thin so Phase 6 can replace it with durable async orchestration without redoing ingest semantics

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-ingest-point-detection*
*Context gathered: 2026-04-23*
