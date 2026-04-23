# Phase 2: Ingest & Point Detection - Research

**Researched:** 2026-04-23
**Domain:** Local file ingest, approved public URL ingest, point-boundary detection, and point persistence for Ultimate game videos. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]
**Confidence:** MEDIUM. Repo seams and package facts are verified; point-fusion details are partly project-specific design guidance. [VERIFIED: src/sva/ingest/ingest.py] [VERIFIED: src/sva/pipeline.py] [VERIFIED: src/sva/models.py]

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** v1 URL ingest is explicitly allowlisted to YouTube and UFA stream pages only. Other URLs return a 400-style validation failure instead of falling through to generic `yt-dlp` behavior. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]
- **D-02:** URL ingest requires an explicit rights acknowledgment on every call. CLI uses `--ack-rights` now; the future HTTP surface carries the equivalent boolean field without changing the decision. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]
- **D-03:** Rights acknowledgment logging stores URL, ISO timestamp, and caller identifier in a dedicated `rights_acks` table. CLI uses a caller-supplied identity now; Phase 7 can map this to `coach_id`. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]
- **D-04:** If `yt-dlp` cannot fetch a URL anonymously, Phase 2 fails loudly with a clear public-URLs-only error. No cookies flow, auth bypass, or private-video support enters v1. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]
- **D-05:** Point detection is a dedicated pre-perception stage inserted between ingest normalization and per-window perception. No downstream window processing begins until boundaries exist. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]
- **D-06:** Boundary detection uses a staged fusion strategy: scoreboard OCR is the primary signal, pull/start-of-play heuristics are the secondary signal, and cheap VLM Q&A is only used to disambiguate candidate spans instead of scanning the entire game. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]
- **D-07:** The detector persists boundary evidence per point candidate, including which signals fired and a confidence score, so later phases and the eventual UI editor can inspect why a boundary was chosen. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]
- **D-08:** Phase 2 should prefer honest partial success over false certainty. If a boundary is uncertain, the system still emits a best-effort point segment with low-confidence evidence rather than fabricating a precise transition. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]
- **D-09:** Phase 2 ships the ingest capability as a backend-first service with thin invocation surfaces, not a coach-facing UI. The canonical surface is a synchronous local/API ingest entrypoint that accepts file upload or approved URL and returns normalized ingest metadata plus detected point boundaries. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]
- **D-10:** Local file support remains broad for `mp4`, `mov`, `m4v`, and `webm`. The same normalization path handles both file and URL sources so there is one ingest baseline, not two divergent codepaths. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]
- **D-11:** The Phase 2 HTTP surface stays intentionally thin: submit file or URL, require rights ack for URLs, return the normalized video/blob metadata and point-boundary output. Durable jobs, polling, and partial-result streaming remain Phase 6 work. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]
- **D-12:** CLI parity is maintained in Phase 2 so the builder can exercise ingest and point detection without going through the HTTP layer. CLI and API must call shared service code rather than duplicating ingest logic. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]
- **D-13:** Phase 2 introduces a first-class point record rather than treating `point_id` as an ad hoc string on events only. Point boundaries need their own persisted rows so later correction and rebucketing work cleanly. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]
- **D-14:** `point_id` is an opaque, stable per-game identifier derived from point order, not from raw timestamps. Timestamp edits should update point boundaries without forcing downstream ids to be renamed. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]
- **D-15:** Events keep their absolute `video_ts_ms` and also gain an explicit in-point timestamp field derived from the enclosing point's start offset. This is a contract requirement for downstream exports and per-point queries, not a UI-only concern. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]
- **D-16:** Downstream phases inherit point assignment from Phase 2 rather than recomputing it. The point detector is the single source of truth for point membership. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]

### Claude's Discretion
- Exact confidence threshold tuning for OCR / heuristic / VLM fusion [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]
- Internal naming of the synchronous Phase 2 HTTP route(s), as long as the surface stays thin and Phase 6 can supersede it cleanly [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]
- Exact storage shape for boundary evidence payloads, as long as it is persisted and queryable [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]

### Deferred Ideas (OUT OF SCOPE)
- None — discussion stayed within phase scope [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INGEST-01 | User can upload a local video file (`mp4`, `mov`, `m4v`, `webm`) via the web UI. [VERIFIED: .planning/REQUIREMENTS.md] | Phase 2 should ship the multipart HTTP contract and shared file-ingest service the later UI calls, even though coach-facing UI work stays deferred. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] |
| INGEST-02 | User can submit a public video URL (YouTube, Vimeo, UFA stream pages) and the system resolves + fetches it. [VERIFIED: .planning/REQUIREMENTS.md] | Phase 2 context narrows v1 execution to allowlisted YouTube and UFA pages with explicit rights ack and anonymous-only fetch; planner should treat the broader REQUIREMENTS wording as constrained by CONTEXT for this phase. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] |
| POINT-01 | System detects point boundaries across a full-game video as a dedicated first pass before per-point processing. [VERIFIED: .planning/REQUIREMENTS.md] | Insert `detect_points()` between normalization and any windowed perception loop; persist points plus evidence before later phases run. [VERIFIED: src/sva/pipeline.py] [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] |
| POINT-03 | Every persisted event carries a `point_id` and an in-point timestamp; every export is sliceable by point. [VERIFIED: .planning/REQUIREMENTS.md] | Add first-class `points` rows, add `in_point_ts_ms` to event persistence, and assign point membership from persisted boundaries instead of recomputing from timestamps later. [VERIFIED: src/sva/models.py] [VERIFIED: src/sva/events_dao.py] [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] |
</phase_requirements>

## Summary

Phase 2 should replace the current `ingest_clip() -> whole-video windows -> interpret one synthetic point` path with `resolve_source -> normalize_video -> detect_points -> persist points`, leaving per-point perception to later phases. The repo today has one local-file ingest path, a `jobs` row, and nullable `events.point_id`, so the phase needs new source-resolution and point-persistence seams rather than prompt work. [VERIFIED: src/sva/ingest/ingest.py] [VERIFIED: src/sva/pipeline.py] [VERIFIED: src/sva/events_dao.py]

The most important planning decision is to keep one normalization path for both local files and approved URLs, and to make points first-class rows now. That avoids two ingest implementations, prevents timestamp-derived point IDs from leaking into downstream code, and gives later phases a stable join target for `WHERE point_id = ?` queries. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] [VERIFIED: src/sva/models.py] [VERIFIED: migrations/versions/0001_phase1_foundation.py]

**Primary recommendation:** Build a shared ingest service that returns a persisted `video` record plus persisted `points`, expose it through thin CLI and FastAPI entrypoints, and make downstream event assignment consume stored point rows only. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] [VERIFIED: .planning/research/SUMMARY.md]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Multipart file upload acceptance | API / Backend | Browser / Client | Phase 2 is explicitly backend-first; the UI later only submits the file to this server contract. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] [CITED: https://fastapi.tiangolo.com/tutorial/request-files/] |
| Approved URL validation and fetch | API / Backend | Database / Storage | Host allowlist, rights ack, anonymous-only fetch, and temp download control belong on the server side. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] |
| Probe + CFR normalization | API / Backend | Database / Storage | The existing repo already probes and transcodes in Python before persistence; Phase 2 should reuse that seam for both sources. [VERIFIED: src/sva/ingest/ingest.py] [VERIFIED: src/sva/ingest/transcode.py] |
| Point-boundary detection fusion | API / Backend | Database / Storage | Fusion logic is a pre-perception processing stage, and its outputs need durable evidence rows for later inspection. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] |
| Point rows and event sliceability | Database / Storage | API / Backend | Queryable `points` and event foreign keys are data-model responsibilities first; API consumers should read them, not infer them. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] [VERIFIED: src/sva/models.py] |

## Project Constraints (from CLAUDE.md)

- Backend work should stay on Python 3.12 with FastAPI as the intended HTTP framework. [VERIFIED: CLAUDE.md]
- Video ingest should stay on PyAV-based handling, with `yt-dlp` used as the restricted URL-ingest tool rather than custom scrapers. [VERIFIED: CLAUDE.md]
- Orchestration should stay thin and plain-Python, not a workflow framework rewrite. [VERIFIED: CLAUDE.md]

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `fastapi` | `0.136.0` published `2026-04-16`. [VERIFIED: PyPI JSON fastapi] | Thin synchronous `/ingest` file-or-URL endpoint. [CITED: https://fastapi.tiangolo.com/tutorial/request-files/] | Official docs recommend `UploadFile` for large uploads, which fits video ingest. [CITED: https://fastapi.tiangolo.com/tutorial/request-files/] |
| `python-multipart` | `0.0.26` published `2026-04-10`. [VERIFIED: PyPI JSON python-multipart] | Multipart parsing for HTTP file upload. [CITED: https://fastapi.tiangolo.com/tutorial/request-files/] | FastAPI requires it for `File`/`UploadFile` handling. [CITED: https://fastapi.tiangolo.com/tutorial/request-files/] |
| `yt-dlp` | `2026.3.17` published `2026-03-17`. [VERIFIED: PyPI JSON yt-dlp] | Approved public URL probe + fetch. [CITED: https://raw.githubusercontent.com/yt-dlp/yt-dlp/master/README.md] | Official embedding docs show `YoutubeDL.extract_info(..., download=False)` for preflight and metadata resolution. [CITED: https://raw.githubusercontent.com/yt-dlp/yt-dlp/master/README.md] |
| `av` | `17.0.1` published `2026-04-18`. [VERIFIED: PyPI JSON av] | Reuse current probe/transcode path after local or URL staging. [VERIFIED: src/sva/ingest/probe.py] [VERIFIED: src/sva/ingest/transcode.py] | Already in repo and environment; no second media path should be introduced. [VERIFIED: pyproject.toml] |
| `sqlalchemy` | `2.0.49` published `2026-04-03`. [VERIFIED: PyPI JSON sqlalchemy] | ORM/DAO layer for `videos`, `rights_acks`, `points`, and event backfills. [VERIFIED: src/sva/events_dao.py] | Matches current project persistence pattern. [VERIFIED: pyproject.toml] |
| `alembic` | `1.18.4` published `2026-02-10`. [VERIFIED: PyPI JSON alembic] | Schema migration path for point tables and new event columns. [VERIFIED: migrations/versions/0001_phase1_foundation.py] | Matches current project migration pattern. [VERIFIED: pyproject.toml] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | `9.0.3` published `2026-04-07`. [VERIFIED: PyPI JSON pytest] | Requirement-level API, DB, and detector tests. [VERIFIED: pyproject.toml] | Use for all automated verification in this phase. [VERIFIED: tests/test_db_migration.py] |

**Installation:** [VERIFIED: pyproject.toml]
```bash
uv add fastapi python-multipart yt-dlp
```

## Architecture Patterns

### System Architecture Diagram

```text
local file upload ─┐
                   ├─> resolve_source() ─> stage local temp path ─> normalize_video()
approved URL ------┘            │                               │
                                │                               ├─> probe_metadata()
                                └─> rights_acks + allowlist     └─> transcode_to_cfr()
                                              │
                                              v
                                       persisted video row
                                              │
                                              v
                                     detect_points(video_id)
                                              │
                 scoreboard OCR candidates ───┼─── pull/start heuristics
                                              │
                                              └─── cheap VLM only on ambiguous spans
                                              │
                                              v
                                   persisted points + evidence
                                              │
                                              v
                                return normalized metadata + boundaries
```

### Recommended Project Structure

```text
src/sva/
├── ingest/
│   ├── service.py        # shared file-or-URL ingest orchestration
│   ├── sources.py        # local source staging + URL allowlist validation
│   ├── url_fetch.py      # yt-dlp adapter only
│   └── api.py            # thin FastAPI route(s), if Phase 2 adds HTTP now
├── points/
│   ├── detector.py       # detect_points entrypoint
│   ├── fusion.py         # OCR/heuristic/VLM fusion policy
│   └── dao.py            # points + evidence persistence
└── pipeline.py           # call detect_points after normalize, before later stages
```

### Pattern 1: One Ingest Baseline for File and URL

**What:** Both source types should converge to the same staged local file before any probe/transcode logic runs. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]  
**When to use:** Always; do not create separate file and URL normalization branches. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]  
**Implementation:** `resolve_source()` should output `{source_kind, staged_path, source_ref, rights_ack_id?}` and `normalize_video()` should accept only that resolved object. [ASSUMED]

### Pattern 2: Preflight URL Before Download

**What:** Parse the URL host, require `ack_rights`, log the ack, call `yt-dlp` metadata preflight with `download=False`, reject unsupported hosts or non-anonymous availability, and only then download into a temp file. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] [CITED: https://raw.githubusercontent.com/yt-dlp/yt-dlp/master/README.md]  
**When to use:** Every URL ingest request. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]  
**Why:** It enforces D-01 through D-04 before any network-heavy fetch. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]

### Pattern 3: Candidate Fusion, Not Whole-Game VLM Scanning

**What:** Run cheap scoreboard OCR and pull/start heuristics over the full normalized video, create candidate boundary spans, and send only ambiguous spans to the cheap VLM tie-breaker. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] [VERIFIED: .planning/research/SUMMARY.md]  
**When to use:** Full-game point detection only. [VERIFIED: .planning/ROADMAP.md]  
**Why:** Project research already flags scoreboard OCR + heuristics as the cheap first pass and warns that no-scoreboard footage needs a fallback rather than false certainty. [VERIFIED: .planning/research/SUMMARY.md] [VERIFIED: .planning/research/PITFALLS.md]

### Pattern 4: First-Class Points, Derived Event Offsets

**What:** Persist `points` rows first, then assign every later event by `point_id` and compute `in_point_ts_ms = video_ts_ms - point.start_video_ts_ms`. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]  
**When to use:** All event persistence after Phase 2. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]  
**Why:** The current repo only stores nullable `events.point_id`; Phase 2 must make point sliceability a storage contract, not a convention. [VERIFIED: src/sva/events_dao.py] [VERIFIED: src/sva/models.py]

### Point / Video Data Model Decisions

- Add a `videos` table now and keep `jobs` as execution state, not canonical video identity. The current `jobs` row stores `game_id`, `video_id`, `source_path`, and `duration_s`, but Phase 2 needs stable source metadata plus future-proof separation from Phase 6 async job IDs. [VERIFIED: src/sva/ingest/ingest.py] [VERIFIED: .planning/research/SUMMARY.md] [ASSUMED]
- Add `rights_acks(id, source_url, caller_id, acked_at, source_kind, video_id nullable)` exactly as a dedicated audit table. That shape directly satisfies D-03 and avoids burying the acknowledgment in logs or JSON blobs. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] [ASSUMED]
- Add `points(point_id, game_id, point_ordinal, start_video_ts_ms, end_video_ts_ms, confidence, status, evidence_summary_json, created_at)` with `UNIQUE(game_id, point_ordinal)` and an index on `(game_id, start_video_ts_ms)`. `point_id` should be generated from order once per persisted point, while `point_ordinal` stays the sortable/display field. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] [ASSUMED]
- Add `point_boundary_evidence(id, game_id, point_id, signal_type, signal_ts_ms, confidence, chosen, payload_json)` instead of storing evidence only in app logs. A separate table is the cleanest way to satisfy D-07's “persisted and inspectable” requirement without hard-coding every future evidence field. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] [ASSUMED]
- Extend `events` with `point_ordinal` and `in_point_ts_ms` and migrate `point_id` toward non-null after the Phase 2 pipeline writes them consistently. Doing it in two steps avoids breaking current Phase 1 tests while still letting Phase 2 end with a hard contract. [VERIFIED: src/sva/models.py] [VERIFIED: src/sva/events_dao.py] [ASSUMED]

### Anti-Patterns to Avoid

- **Two ingest pipelines:** Do not keep one local-file normalization path and a second URL-only normalization path. The phase context explicitly forbids divergent baselines. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]
- **Whole-game VLM point scan:** Do not ask the VLM to scan every minute of the game for boundaries. The locked fusion order makes VLM a tie-breaker only. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]
- **Timestamp-derived `point_id`:** Do not encode `start_video_ts_ms` into the ID. Boundary edits would rename downstream joins. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]
- **Evidence only in logs:** Do not persist boundary rationale only through observability traces. The UI/editor path needs queryable evidence rows later. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Multipart upload parsing | Custom request-body parsing | `FastAPI UploadFile` + `python-multipart` | Official docs already support large spooled uploads without reading the full file into memory. [CITED: https://fastapi.tiangolo.com/tutorial/request-files/] |
| Public video site extraction | Custom YouTube/UFA HTML scrapers | `yt-dlp` adapter behind a small service wrapper | Official embedding docs support metadata preflight and fetch; scrapers will break faster. [CITED: https://raw.githubusercontent.com/yt-dlp/yt-dlp/master/README.md] |
| Point membership inference in every phase | Recompute point slices from raw timestamps later | Persist `points` once and join by `point_id` | D-16 explicitly makes Phase 2 the single source of truth. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] |

## Common Pitfalls

### Pitfall 1: Treating `jobs` as the only video record

**What goes wrong:** Ingest metadata, source provenance, and future async execution state get conflated into one row. [VERIFIED: src/sva/ingest/ingest.py]  
**Why it happens:** Phase 1 only needed a narrow vertical slice, so `jobs` currently doubles as the ingest metadata table. [VERIFIED: .planning/ROADMAP.md]  
**How to avoid:** Introduce `videos` now and let `jobs` remain process/run state. [VERIFIED: .planning/research/SUMMARY.md] [ASSUMED]  
**Warning signs:** Planner tasks talk about “adding fields to jobs” for source provenance instead of adding a dedicated asset table. [ASSUMED]

### Pitfall 2: Boundary precision theatre

**What goes wrong:** The detector invents exact cut points even when scoreboard and heuristics disagree. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]  
**Why it happens:** It is tempting to collapse all ambiguity into one “best” timestamp. [ASSUMED]  
**How to avoid:** Persist low-confidence best-effort points and the evidence that made them ambiguous. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]  
**Warning signs:** No confidence or evidence payload is stored for a point row. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]

### Pitfall 3: Network-dependent CI for URL ingest

**What goes wrong:** CI fails because a public URL changed, throttled, or disappeared. [ASSUMED]  
**Why it happens:** URL ingest is validated only with live network tests. [ASSUMED]  
**How to avoid:** Unit-test URL resolution with a mocked `yt-dlp` adapter and keep live public-URL verification as a manual smoke test. [ASSUMED]  
**Warning signs:** A required test depends on YouTube/UFA uptime. [ASSUMED]

## Code Examples

### Thin FastAPI file-or-url endpoint

Source: FastAPI request-files docs for `UploadFile`; adapted to Phase 2's shared service shape. [CITED: https://fastapi.tiangolo.com/tutorial/request-files/]

```python
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

router = APIRouter()


@router.post("/ingest")
async def ingest_endpoint(
    file: Annotated[UploadFile | None, File()] = None,
    url: Annotated[str | None, Form()] = None,
    ack_rights: Annotated[bool, Form()] = False,
    caller_id: Annotated[str | None, Form()] = None,
):
    if bool(file) == bool(url):
        raise HTTPException(status_code=400, detail="Provide exactly one of file or url")
    return await ingest_service.ingest(file=file, url=url, ack_rights=ack_rights, caller_id=caller_id)
```

### `yt-dlp` preflight before download

Source: yt-dlp embedding docs for `YoutubeDL` and `extract_info(..., download=False)`; adapted to the phase allowlist rules. [CITED: https://raw.githubusercontent.com/yt-dlp/yt-dlp/master/README.md]

```python
from yt_dlp import YoutubeDL


def preflight_url(url: str) -> dict:
    with YoutubeDL({"quiet": True, "noplaylist": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    availability = info.get("availability")
    if availability not in {"public", "unlisted", None}:
        raise ValueError("public-urls-only")
    return info
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `run_pipeline()` windows the whole ingested clip immediately after `ingest_clip()`. [VERIFIED: src/sva/pipeline.py] | Phase 2 should detect and persist points before any downstream windowing. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] | 2026-04-23 phase context lock. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] | Later stages can become per-point and sliceable by construction. [VERIFIED: .planning/ROADMAP.md] |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | A dedicated `videos` table should be introduced now instead of further extending `jobs`. | Point / Video Data Model Decisions | Medium — planner may otherwise overfit Phase 2 to a schema that Phase 6 must later undo. |
| A2 | A separate `point_boundary_evidence` table is preferable to a single JSONB blob on `points`. | Point / Video Data Model Decisions | Low — either shape can work if evidence stays queryable. |
| A3 | URL ingest tests should stub `yt-dlp` in CI and reserve live public URLs for manual smoke testing. | Common Pitfalls / Validation Architecture | Low — CI could still be made networked, but reliability will drop. |

## Open Questions

1. **Exact UFA allowlist hostnames**
   - What we know: `watchufa.com` is the official site, and it links to `watchufa.tv` for streaming. [CITED: https://watchufa.com/node/7769]
   - What's unclear: Whether Phase 2 should allow only `watchufa.com` pages, only `watchufa.tv`, or both plus `www.` variants. [ASSUMED]
   - Recommendation: Lock the exact hostname set in the plan and unit-test it explicitly rather than hiding it in permissive regex logic. [ASSUMED]

2. **Scoreboard OCR engine selection**
   - What we know: The locked architecture requires scoreboard OCR as the primary point-boundary signal. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]
   - What's unclear: The specific OCR package is not locked by current docs or context. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md]
   - Recommendation: Keep OCR behind one `ScoreboardOCR` adapter file and choose the concrete engine during planning Wave 0 so it does not leak into the rest of the design. [ASSUMED]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `.venv/bin/python` | Phase 2 implementation runtime | ✓ | `Python 3.12.13` [VERIFIED: local command] | — |
| `.venv/bin/pytest` | Automated verification | ✓ | `pytest 9.0.3` [VERIFIED: local command] | — |
| `ffmpeg` | Fixture generation and media toolchain sanity checks | ✓ | `8.1` [VERIFIED: local command] | PyAV path still works, but fixture generation becomes harder. [ASSUMED] |
| `fastapi` | Thin HTTP ingest surface | ✗ in current venv | — [VERIFIED: local import check] | CLI-only testing until installed. [VERIFIED: src/sva/cli.py] |
| `yt_dlp` | Approved URL ingest | ✗ in current venv | — [VERIFIED: local import check] | None for Phase 2 URL ingest. |
| Postgres service | DB-backed integration tests and migrations | ✗ running locally right now | connection refused on `127.0.0.1:5432`. [VERIFIED: local command] | Unit tests can mock DAOs, but requirement-level DB coverage still needs Postgres. [VERIFIED: tests/test_db_migration.py] |

**Missing dependencies with no fallback:**
- `yt_dlp` for INGEST-02 implementation. [VERIFIED: local import check]
- Running Postgres for migration and integration tests. [VERIFIED: local command]

**Missing dependencies with fallback:**
- `fastapi` in the current venv; CLI parity can be built first, but the HTTP contract cannot be verified until installed. [VERIFIED: local import check] [VERIFIED: src/sva/cli.py]

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest 9.0.3`. [VERIFIED: pyproject.toml] [VERIFIED: local command] |
| Config file | `pyproject.toml`. [VERIFIED: pyproject.toml] |
| Quick run command | `uv run pytest -q tests/test_ingest_phase2_api.py tests/test_point_detection_phase2.py`. [ASSUMED] |
| Full suite command | `uv run pytest -q`. [VERIFIED: pyproject.toml] |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INGEST-01 | Multipart upload accepts one allowed local video file and returns normalized metadata from the shared service. [VERIFIED: .planning/REQUIREMENTS.md] | API integration | `uv run pytest -q tests/test_ingest_phase2_api.py::test_file_upload_returns_normalized_video` | ❌ Wave 0 |
| INGEST-02 | URL path rejects missing ack / disallowed hosts / non-public fetch and accepts approved public URLs through the shared normalization path. [VERIFIED: .planning/REQUIREMENTS.md] | service + API | `uv run pytest -q tests/test_ingest_phase2_url.py` | ❌ Wave 0 |
| POINT-01 | Point detector runs before later window processing and persists boundaries plus evidence. [VERIFIED: .planning/REQUIREMENTS.md] | service + DB integration | `uv run pytest -q tests/test_point_detection_phase2.py::test_detect_points_persists_points_before_downstream_processing` | ❌ Wave 0 |
| POINT-03 | Event rows receive non-null `point_id` and `in_point_ts_ms`; queries scoped by `point_id` return only that point's events. [VERIFIED: .planning/REQUIREMENTS.md] | DB integration | `uv run pytest -q tests/test_point_assignment_phase2.py` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** run the targeted Phase 2 pytest module(s). [ASSUMED]
- **Per wave merge:** run `uv run pytest -q`. [VERIFIED: pyproject.toml]
- **Phase gate:** run full suite green with Postgres up and one manual approved-URL smoke test. [VERIFIED: tests/test_db_migration.py] [ASSUMED]

### Wave 0 Gaps

- [ ] `tests/test_ingest_phase2_api.py` — multipart upload contract, mutual exclusivity of `file` vs `url`, and allowed extension coverage. [ASSUMED]
- [ ] `tests/test_ingest_phase2_url.py` — host allowlist, rights-ack requirement, anonymous-only failure path, and shared normalization assertions. [ASSUMED]
- [ ] `tests/test_point_detection_phase2.py` — candidate fusion order, ambiguity fallback, and evidence persistence. [ASSUMED]
- [ ] `tests/test_point_assignment_phase2.py` — `point_id` + `in_point_ts_ms` persistence and SQL sliceability checks. [ASSUMED]
- [ ] Postgres runtime for DB-backed tests: `docker compose up -d db`. [VERIFIED: tests/test_db_migration.py]

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth work is added in this phase. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] |
| V3 Session Management | no | No session surface is introduced in this phase. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] |
| V4 Access Control | no | The phase is backend-first and single-user/developer-facing for now. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] |
| V5 Input Validation | yes | Validate extension, parsed media metadata, URL hostname allowlist, and `ack_rights` before fetch/transcode. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] [CITED: https://fastapi.tiangolo.com/tutorial/request-files/] |
| V6 Cryptography | no | No crypto design is introduced here. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] |

### Known Threat Patterns for Phase 2

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Arbitrary URL fetch through ingest | Tampering | Hard host allowlist, no cookies, anonymous-only fetch, and explicit rights ack logging before `yt-dlp` download. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] |
| Oversized or invalid uploads | Denial of Service | Use `UploadFile`, stage to temp storage, then probe metadata and reject unsupported containers early. [CITED: https://fastapi.tiangolo.com/tutorial/request-files/] [VERIFIED: src/sva/ingest/probe.py] |
| Path traversal via original filename | Tampering | Never trust the upload filename for server storage paths; generate `video_id`-based paths only. [VERIFIED: src/sva/ingest/ingest.py] [ASSUMED] |
| Private/auth-only media access | Information Disclosure | Treat `yt-dlp` preflight availability like a hard gate and return a public-URLs-only error. [VERIFIED: .planning/phases/02-ingest-point-detection/02-CONTEXT.md] [CITED: https://raw.githubusercontent.com/yt-dlp/yt-dlp/master/README.md] |

## Sources

### Primary (HIGH confidence)
- `.planning/phases/02-ingest-point-detection/02-CONTEXT.md` - locked phase decisions, phase scope, and discretion areas.
- `.planning/ROADMAP.md` - Phase 2 success criteria and ordering within the roadmap.
- `.planning/REQUIREMENTS.md` - INGEST-01, INGEST-02, POINT-01, POINT-03 definitions.
- `src/sva/ingest/ingest.py`, `src/sva/pipeline.py`, `src/sva/models.py`, `src/sva/events_dao.py`, `migrations/versions/0001_phase1_foundation.py` - current implementation seams and schema gaps.
- FastAPI request files docs - `https://fastapi.tiangolo.com/tutorial/request-files/`
- FastAPI docs via Context7 - `/fastapi/fastapi` topic `request files UploadFile python-multipart`
- yt-dlp README / embedding docs - `https://raw.githubusercontent.com/yt-dlp/yt-dlp/master/README.md`
- PyPI JSON endpoints for `fastapi`, `python-multipart`, `yt-dlp`, `sqlalchemy`, `alembic`, `av`, and `pytest`

### Secondary (MEDIUM confidence)
- `.planning/research/SUMMARY.md` - prior project research on phase ordering and the point-detection boundary.
- `.planning/research/PITFALLS.md` - prior project-specific ingest and point-detection pitfalls.
- Official UFA schedule page - `https://watchufa.com/node/7769`

### Tertiary (LOW confidence)
- None. All unverified design choices are listed explicitly in the Assumptions Log. [VERIFIED: this document]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - package versions and framework behavior were verified against PyPI and official docs. [VERIFIED: PyPI JSON fastapi] [VERIFIED: PyPI JSON yt-dlp] [CITED: https://fastapi.tiangolo.com/tutorial/request-files/]
- Architecture: MEDIUM - repo seams are verified, but some table-shape recommendations are design choices rather than existing facts. [VERIFIED: src/sva/pipeline.py] [VERIFIED: src/sva/ingest/ingest.py] [ASSUMED]
- Pitfalls: MEDIUM - project docs and current code support them, but exact detector behavior still needs empirical fixtures. [VERIFIED: .planning/research/PITFALLS.md] [ASSUMED]

**Research date:** 2026-04-23
**Valid until:** 2026-05-23 for repo facts; re-check package versions sooner if Phase 2 starts later. [VERIFIED: this document] [ASSUMED]
