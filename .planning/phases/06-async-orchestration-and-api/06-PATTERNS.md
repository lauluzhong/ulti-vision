# Phase 06: Async Orchestration & API - Pattern Map

**Mapped:** 2026-04-24
**Scope source:** `06-CONTEXT.md` + `.planning/ROADMAP.md` + live codebase
**Files analyzed:** 10 likely Phase 6 files
**Analogs found:** 9 / 10

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/sva/api/app.py` | controller | request-response | `src/sva/api/app.py` | self |
| `src/sva/jobs_dao.py` | service | CRUD | `src/sva/events_dao.py` + `src/sva/ingest/ingest.py` | composite |
| `src/sva/pipeline.py` | service | batch | `src/sva/pipeline.py` + `src/sva/perceive/runner.py` | self+support |
| `src/sva/exports.py` | utility | file-I/O, transform | `src/sva/events_dao.py` | partial |
| `src/sva/ingest/ingest.py` | model/service | CRUD | `src/sva/ingest/ingest.py` | self |
| `migrations/versions/0009_phase6_async_jobs_api.py` | migration | CRUD | `migrations/versions/0007_phase5_memory_and_corrections.py` + `0001_phase1_foundation.py` | exact |
| `tests/test_ingest_api.py` | test | request-response | `tests/test_ingest_api.py` | self |
| `tests/test_point_scoped_pipeline.py` or `tests/test_async_pipeline.py` | test | batch | `tests/test_point_scoped_pipeline.py` | self |
| `tests/test_db_migration.py` | test | migration | `tests/test_db_migration.py` | self |
| `src/sva/worker.py` or `src/sva/queue.py` | service | event-driven | no close analog | none |

## Pattern Assignments

### `src/sva/api/app.py` (controller, request-response)

**Analog:** [src/sva/api/app.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/api/app.py:39)

**FastAPI composition root** ([src/sva/api/app.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/api/app.py:39)):
```python
def create_app() -> Any:
    if FastAPI is None:
        raise RuntimeError("fastapi is not installed. Install project dependencies to use the API surface.")

    app = FastAPI(title="Sports Video Analytics API", version="0.1.0")
```

**Route validation + exception translation** ([src/sva/api/app.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/api/app.py:45)):
```python
@app.post("/ingest")
async def ingest_endpoint(...):
    if (upload is None and url is None) or (upload is not None and url is not None):
        raise HTTPException(status_code=400, detail="Provide exactly one source: either a file upload or a public URL.")
    try:
        ...
    except SourcePolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

**Upload persistence helper** ([src/sva/api/app.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/api/app.py:30)):
```python
def _save_upload(upload: Any) -> Path:
    suffix = Path(upload.filename or "upload.bin").suffix or ".bin"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dst = UPLOAD_DIR / f"upload_{uuid.uuid4().hex}{suffix}"
```

**Phase 6 guidance**
- Keep `create_app()` as the single HTTP composition root.
- Keep input validation and `HTTPException` mapping in the route; delegate orchestration, status lookup, correction writing, and CSV generation to service helpers.
- Preserve the current source branching for file upload vs public URL; only the response changes from serialized ingest metadata to immediate async job submission data.
- Add `GET /jobs/{id}`, `GET /games/{id}/events`, `POST /games/{id}/corrections`, and `GET /exports/{game_id}.csv` in the same thin-controller style unless the file becomes unwieldy.

---

### `src/sva/jobs_dao.py` plus `src/sva/ingest/ingest.py` (service/model, CRUD)

**Primary analogs:** [src/sva/ingest/ingest.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/ingest/ingest.py:35), [src/sva/events_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/events_dao.py:78)

**Canonical `jobs` row lives here already** ([src/sva/ingest/ingest.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/ingest/ingest.py:35)):
```python
class JobRow(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    game_id = Column(Text, nullable=False, unique=True, index=True)
    video_id = Column(Text, nullable=False)
    status = Column(Text, nullable=False, server_default="pending")
```

**Existing insert shape** ([src/sva/ingest/ingest.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/ingest/ingest.py:96)):
```python
with session_scope() as session:
    row = JobRow(
        game_id=game_id,
        video_id=video_id,
        status="ingested",
        source_path=str(src.resolve()),
        source_kind=source_kind,
        source_url=source_url,
        duration_s=out_meta.duration_s,
    )
    session.add(row)
```

**Filtered DAO query pattern to copy** ([src/sva/events_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/events_dao.py:78)):
```python
def list_event_rows(game_id: str, *, point_id: str | None = None, event_type: str | None = None, team: str | None = None) -> list[EventRow]:
    with session_scope() as session:
        stmt = select(EventRow).where(EventRow.game_id == game_id)
        if point_id is not None:
            stmt = stmt.where(EventRow.point_id == point_id)
```

**Phase 6 guidance**
- Keep `JobRow` as the canonical lifecycle anchor per `D-04`; extend this row in place if Phase 6 needs stage fields or progress JSON.
- Put read/update helpers in a narrow `jobs_dao.py` instead of bloating `ingest.py` with status-transition logic.
- Mirror existing DAO style: one row class source of truth, then small helpers like `get_job(game_id)`, `update_job_status(...)`, `record_job_progress(...)`, `list_job_partial_points(...)`.
- Every status transition should update `updated_at`; pollers must read persisted truth, not worker memory.

---

### `src/sva/pipeline.py` (service, resumable batch orchestration)

**Primary analog:** [src/sva/pipeline.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/pipeline.py:109)  
**Supportive analog:** [src/sva/perceive/runner.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/perceive/runner.py:69)

**Current orchestration seam** ([src/sva/pipeline.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/pipeline.py:109)):
```python
def run_pipeline(
    source_path: Path | str,
    game_id: str | None = None,
    *,
    target_fps: int = 1,
) -> PipelineResult:
    ing = ingest_clip(source_path, game_id=game_id, target_fps=target_fps)
    ...
    point_candidates = _build_point_boundary_candidates(ing)
    points = detect_points(ing.game_id, point_candidates)
    ...
    for start_ms, end_ms in ing.windows:
        ...
        obs = run_window(...)
    ...
    for point_id, point_observations in observations_by_point.items():
        ...
        events = run_point(...)
        insert_events(scoped_events)
```

**Existing stage-order helper** ([src/sva/pipeline.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/pipeline.py:86)):
```python
def _resolve_window_point(points: list[PointRecord], start_ms: int, end_ms: int) -> PointRecord | None:
    midpoint_ms = (start_ms + end_ms) // 2
    for point in points:
        if point.start_video_ts_ms <= midpoint_ms <= point.end_video_ts_ms:
            return point
```

**Cache-first resume seam to preserve** ([src/sva/perceive/runner.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/perceive/runner.py:69)):
```python
def run_window(...):
    prompt_hash = _prompt_hash_for_window(p, window)
    if prompt_hash is not None:
        cached = list_cached_observations(
            video_id=window.video_id,
            window_id=window.window_id,
            prompt_version_hash=prompt_hash,
        )
        if cached:
            _emit_cache_hit_trace(effective_ctx)
            return cached[0]
```

**Ordering test pattern** ([tests/test_point_scoped_pipeline.py](/Users/lauluzhong/Documents/Sports Video Analytics/tests/test_point_scoped_pipeline.py:152)):
```python
monkeypatch.setattr("sva.pipeline.ingest_clip", fake_ingest_clip)
...
result = run_pipeline("tests/fixtures/cfr_baseline.mp4", game_id="game_test")
second_result = run_pipeline("tests/fixtures/cfr_baseline.mp4", game_id="game_test")
assert order.index("detect") < order.index("perceive:game_test:pt_001")
assert perceive_calls["count"] == 2
```

**Phase 6 guidance**
- Do not replace the current control flow wholesale; factor it into resumable stage helpers that still preserve the existing ingest -> point-detect -> perceive -> interpret -> persist order.
- Resume decisions should be made by inspecting persisted `jobs`, `points`, `observations`, and `events`, not by ephemeral actor-local state.
- Keep the queue-specific wrapper thin; the durable Python service should remain callable directly from tests.
- Reuse `run_window()` exactly as the perception boundary so completed `(video_id, window_id, prompt_version_hash)` windows do not re-hit Gemini after restart.

---

### `src/sva/exports.py` (utility, file-I/O + transform)

**Closest analog:** [src/sva/events_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/events_dao.py:78)  
**Supportive analog:** [src/sva/api/app.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/api/app.py:23)

**Filtered canonical read pattern** ([src/sva/events_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/events_dao.py:78)):
```python
def list_event_rows(...):
    ...
    return list(
        session.execute(
            stmt.order_by(EventRow.video_ts_ms.asc(), EventRow.event_id.asc())
        ).scalars()
    )
```

**Small serializer helper style** ([src/sva/api/app.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/api/app.py:23)):
```python
def _serialize_ingest_result(result: Any) -> dict[str, Any]:
    payload = asdict(result)
    payload["source_metadata"] = result.source_metadata.model_dump()
    payload["transcoded_metadata"] = result.transcoded_metadata.model_dump()
    return payload
```

**Phase 6 guidance**
- Build CSV from canonical stored `EventRow` reads, not from observations, raw model responses, or recomputed point state.
- Keep export logic as a small pure transform helper: rows in, stable header + CSV bytes/string out.
- Introduce a versioned header constant in the export module; keep internal IDs like `event_id`, `source_observations`, and `memory_refs` out of the user-facing CSV.
- Route code should only wrap the output in the FastAPI response object and headers.

---

### Correction submission handling (`POST /games/{id}/corrections`)

**Primary analogs:** [src/sva/memory/__init__.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/memory/__init__.py:3), [src/sva/memory/corrections_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/memory/corrections_dao.py:52), [src/sva/memory/writer.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/memory/writer.py:32), [src/sva/memory/records_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/memory/records_dao.py:110)

**Public memory exports already expose the thin write path** ([src/sva/memory/__init__.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/memory/__init__.py:3)):
```python
from sva.memory.corrections_dao import insert_corrections, list_corrections
from sva.memory.records_dao import insert_memory_records, list_memory_records
from sva.memory.writer import can_promote_global, correction_to_memory_records, promote_memory_record
```

**Immutable correction insert pattern** ([src/sva/memory/corrections_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/memory/corrections_dao.py:52)):
```python
def insert_corrections(records: list[CorrectionRecord]) -> None:
    if not records:
        return
    with session_scope() as session:
        session.add_all([CorrectionRow(...) for record in records])
```

**Deterministic correction -> memory transform** ([src/sva/memory/writer.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/memory/writer.py:32)):
```python
def correction_to_memory_records(
    correction: CorrectionRecord,
    *,
    created_at: datetime | None = None,
) -> list[MemoryRecord]:
    return [MemoryRecord(..., scope=f"coach:{correction.coach_id}", ...)]
```

**Canonical memory persistence** ([src/sva/memory/records_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/memory/records_dao.py:110)):
```python
def insert_memory_records(records: list[MemoryRecord]) -> None:
    if not records:
        return
    with session_scope() as session:
        session.add_all([MemoryRecordRow(...) for record in records])
```

**Phase 6 guidance**
- Keep the HTTP correction endpoint as a thin adapter over the existing Phase 5 path.
- The write order should stay: validate request -> persist immutable correction row -> derive coach-scoped memory rows -> persist memory rows.
- Do not mutate canonical event rows in place; Phase 5 established corrections as first-class immutable records.
- If the API needs a helper, make it a tiny service function that composes the existing memory exports rather than reimplementing their internals.

---

### `migrations/versions/0009_phase6_async_jobs_api.py` (migration, CRUD)

**Analogs:** [migrations/versions/0007_phase5_memory_and_corrections.py](/Users/lauluzhong/Documents/Sports Video Analytics/migrations/versions/0007_phase5_memory_and_corrections.py:21), [migrations/versions/0001_phase1_foundation.py](/Users/lauluzhong/Documents/Sports Video Analytics/migrations/versions/0001_phase1_foundation.py:25)

**Create-table / create-index pattern** ([migrations/versions/0007_phase5_memory_and_corrections.py](/Users/lauluzhong/Documents/Sports Video Analytics/migrations/versions/0007_phase5_memory_and_corrections.py:21)):
```python
def upgrade() -> None:
    op.create_table(
        "memory_records",
        sa.Column(...),
    )
    op.create_index("ix_memory_records_kind", "memory_records", ["kind"], unique=False)
```

**Existing `jobs` substrate** ([migrations/versions/0001_phase1_foundation.py](/Users/lauluzhong/Documents/Sports Video Analytics/migrations/versions/0001_phase1_foundation.py:25)):
```python
op.create_table(
    "jobs",
    sa.Column("game_id", sa.Text(), nullable=False, index=True, unique=True),
    sa.Column("video_id", sa.Text(), nullable=False),
    sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
```

**Phase 6 guidance**
- Extend `jobs` or add one adjacent progress table with a foreign key back to `jobs.game_id`; do not create a competing job-truth table.
- Keep the migration narrow and query-driven: only add columns and indexes that `GET /jobs/{id}` polling and resume logic actually use.
- Follow the repo pattern of explicit `upgrade()` / `downgrade()` with simple `op.create_*` and `op.drop_*` calls.

---

### Tests

**Route tests:** [tests/test_ingest_api.py](/Users/lauluzhong/Documents/Sports Video Analytics/tests/test_ingest_api.py:41)
```python
monkeypatch.setattr("sva.api.app.ingest_source", _fake_ingest)
client = TestClient(create_app())
response = client.post("/ingest", ...)
assert response.status_code == 200
```

**Orchestration tests:** [tests/test_point_scoped_pipeline.py](/Users/lauluzhong/Documents/Sports Video Analytics/tests/test_point_scoped_pipeline.py:13)
```python
def test_run_pipeline_detects_points_before_perception_and_persists_point_scoped_events(monkeypatch):
    ...
    monkeypatch.setattr("sva.pipeline.run_point", fake_run_point)
    ...
    assert perceive_calls["count"] == 2
```

**Migration smoke tests:** [tests/test_db_migration.py](/Users/lauluzhong/Documents/Sports Video Analytics/tests/test_db_migration.py:27)
```python
@pytest.fixture(scope="module")
def migrated_db():
    subprocess.run(["alembic", "upgrade", "head"], check=True, env=env)
```

**DAO filter tests:** [tests/test_events_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/tests/test_events_dao.py:101), [tests/test_corrections_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/tests/test_corrections_dao.py:36)

**Phase 6 guidance**
- Keep route tests monkeypatch-heavy and DB-free where possible.
- Keep orchestration tests focused on stage ordering, skip/resume behavior, and “no duplicate perceive call” guarantees.
- Add DB-gated tests for any schema additions and for filtered job/event/correction reads that back the API.

## Shared Patterns

### Thin controller boundary
**Source:** [src/sva/api/app.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/api/app.py:45)  
Apply to all new HTTP routes.

```python
if invalid_input:
    raise HTTPException(status_code=400, detail="...")
try:
    result = service(...)
except DomainError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc
```

### Narrow DAO shape
**Source:** [src/sva/events_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/events_dao.py:40), [src/sva/points/dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/points/dao.py:29)  
Apply to jobs/progress helpers and any export read helpers.

```python
def _row_from_model(...): ...
def insert_...(records: list[...]) -> None: ...
def list_...(...filters...) -> list[...]: ...
```

### Resume truth from persisted artifacts
**Source:** [src/sva/perceive/runner.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/perceive/runner.py:77), [src/sva/observations_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/observations_dao.py:72)  
Apply to orchestration and job-status reporting.

```python
cached = list_cached_observations(video_id=..., window_id=..., prompt_version_hash=...)
if cached:
    return cached[0]
```

### Immutable correction write-through
**Source:** [src/sva/memory/corrections_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/memory/corrections_dao.py:52), [src/sva/memory/writer.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/memory/writer.py:32), [src/sva/memory/records_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/memory/records_dao.py:110)  
Apply to `POST /games/{id}/corrections`.

```python
insert_corrections([correction])
memory_records = correction_to_memory_records(correction)
insert_memory_records(memory_records)
```

### Package export style
**Source:** [src/sva/memory/__init__.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/memory/__init__.py:3), [src/sva/api/__init__.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/api/__init__.py:3)  
Apply to any new `jobs_dao`, export, or worker package surface.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `src/sva/worker.py` or `src/sva/queue.py` | service | event-driven | The repo has no existing Dramatiq/Redis/worker bootstrap code. Keep the queue wrapper thin around pure-Python orchestration and follow `.planning/research/SUMMARY.md` for framework specifics. |

## Metadata

**Analog search scope:** `src/sva/api`, `src/sva/ingest`, `src/sva/pipeline.py`, `src/sva/perceive`, `src/sva/events_dao.py`, `src/sva/points`, `src/sva/memory`, `migrations/versions`, `tests`  
**Files scanned:** 22  
**Pattern extraction date:** 2026-04-24
