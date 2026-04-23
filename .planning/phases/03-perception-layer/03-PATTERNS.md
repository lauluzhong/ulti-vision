# Phase 3: Perception Layer - Pattern Map

**Mapped:** 2026-04-23
**Files classified:** 10
**Analogs found:** 10 / 10

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/sva/perceive/adapters/gemini.py` | service | request-response | `src/sva/interpret/adapters/claude.py` | exact |
| `src/sva/perceive/runner.py` | service | request-response | `src/sva/perceive/runner.py` | exact |
| `src/sva/perceive/dao.py` | service | CRUD | `src/sva/points/dao.py` | exact |
| `migrations/versions/0005_phase3_observations.py` | migration | CRUD | `migrations/versions/0003_phase2_points.py` | exact |
| `src/sva/observability/langfuse.py` | utility | request-response | `src/sva/observability/langfuse.py` | exact |
| `src/sva/pipeline.py` | service | batch | `src/sva/pipeline.py` | exact |
| `tests/test_perceive_adapter.py` | test | request-response | `tests/test_perceive_adapter.py` | exact |
| `tests/test_swap_safe_contract.py` | test | request-response | `tests/test_swap_safe_contract.py` | exact |
| `tests/test_point_scoped_pipeline.py` | test | batch | `tests/test_point_scoped_pipeline.py` | exact |
| `tests/test_observations_dao.py` | test | CRUD | `tests/test_observability.py` | role-match |

## Pattern Assignments

### `src/sva/perceive/adapters/gemini.py` (service, request-response)

**Primary analog:** `src/sva/interpret/adapters/claude.py`

**Keep the stub-to-real adapter shape** from [src/sva/interpret/adapters/claude.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/interpret/adapters/claude.py:20) lines 20-48:

```python
@observe_call(stage="interpret", model=_MODEL_ID)
def _call_claude(
    ctx: TraceContext,
    observations: list[Observation],
    retrieved: list[MemoryRecord],
) -> tuple[Event, Decimal, int, int, TraceContext]:
    input_tokens = 500 + 100 * len(observations) + 80 * len(retrieved)
    output_tokens = 100
    cost = estimate_claude_cost(input_tokens, output_tokens, model=_MODEL_ID)

    event = Event(...)
    return (event, cost, input_tokens, output_tokens, ctx)
```

**Keep the public class method thin** from [src/sva/interpret/adapters/claude.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/interpret/adapters/claude.py:51) lines 51-72:

```python
class ClaudeInterpreter:
    model_id: str = _MODEL_ID
    provider: str = "anthropic"

    def interpret(self, ctx: TraceContext, observations: list[Observation], retrieved: list[MemoryRecord]) -> Event:
        enriched = TraceContext(
            stage="interpret",
            model=_MODEL_ID,
            video_id=ctx.video_id,
            game_id=ctx.game_id,
            window_id=ctx.window_id,
            point_id=ctx.point_id,
            point_ordinal=ctx.point_ordinal,
        )
        return _call_claude(enriched, observations, retrieved)
```

**Preserve the current perception-side TraceContext enrichment** from [src/sva/perceive/adapters/gemini.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/perceive/adapters/gemini.py:68) lines 68-78:

```python
def perceive(self, ctx: TraceContext, window: PerceiveWindow) -> Observation:
    enriched = TraceContext(
        stage="perceive",
        model=_MODEL_ID,
        video_id=ctx.video_id,
        game_id=ctx.game_id,
        window_id=window.window_id,
        point_id=ctx.point_id,
        point_ordinal=ctx.point_ordinal,
    )
    return _call_gemini(enriched, window)
```

**Contract boundary to preserve:** `Observation.raw_response_ref` already exists in [src/sva/models.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/models.py:80) lines 80-100, so the real Gemini body should keep returning canonical `Observation` and hang provider payloads off `raw_response_ref`, not leak provider JSON into downstream code.

### `src/sva/perceive/runner.py` (service, request-response)

**Primary analog:** `src/sva/perceive/runner.py`

**Keep the single swap point exactly here** from [src/sva/perceive/runner.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/perceive/runner.py:11) lines 11-16:

```python
def make_default_perceiver() -> Perceiver:
    """Single import-swap point for switching the default VLM backend (D-03)."""
    return GeminiPerceiver()
```

**Keep `run_window` as the one orchestration seam** from [src/sva/perceive/runner.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/perceive/runner.py:19) lines 19-26:

```python
def run_window(
    ctx: TraceContext,
    window: PerceiveWindow,
    perceiver: Perceiver | None = None,
) -> Observation:
    p = perceiver or make_default_perceiver()
    return p.perceive(ctx, window)
```

**Cache insertion point:** put persisted-cache lookup in this function before `p.perceive(...)`. Nothing downstream branches on provider today; keep that invariant so cache hit and live Gemini call both return canonical `Observation` from the same seam.

**Call-site shape to preserve:** [src/sva/pipeline.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/pipeline.py:148) lines 148-160 shows the runner already receives full `TraceContext` and its return value is appended directly into downstream collections:

```python
window_ctx = TraceContext(
    stage="perceive",
    model=getattr(perceiver, "model_id", "unknown"),
    video_id=ing.video_id,
    game_id=ing.game_id,
    window_id=window.window_id,
    point_id=owning_point.point_id,
    point_ordinal=owning_point.point_ordinal,
)
obs = run_window(window_ctx, window, perceiver=perceiver)
observations.append(obs)
observations_by_point[owning_point.point_id].append(obs)
```

### `src/sva/perceive/dao.py` (service, CRUD)

**Primary analogs:** `src/sva/points/dao.py`, `src/sva/events_dao.py`

**Row class style:** copy the ORM declaration style from [src/sva/points/dao.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/points/dao.py:13) lines 13-27:

```python
class PointRow(Base):
    __tablename__ = "points"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    point_id = Column(Text, nullable=False, unique=True)
    game_id = Column(Text, ForeignKey("jobs.game_id", ondelete="CASCADE"), nullable=False, index=True)
    point_ordinal = Column(Integer, nullable=False)
    start_video_ts_ms = Column(BigInteger, nullable=False)
    end_video_ts_ms = Column(BigInteger, nullable=False)
    confidence = Column(Numeric(4, 3), nullable=False)
    boundary_evidence = Column(JSONB, nullable=False, server_default="[]")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
```

**Write path style:** copy the small DAO transaction boundary from [src/sva/events_dao.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/events_dao.py:35) lines 35-54:

```python
def insert_event(event: Event) -> None:
    with session_scope() as session:
        row = EventRow(
            event_id=event.event_id,
            game_id=event.game_id,
            point_id=event.point_id,
            point_ordinal=event.point_ordinal,
            video_ts_ms=event.video_ts_ms,
            in_point_ts_ms=event.in_point_ts_ms,
            type=event.type,
            team=event.team,
            details=event.details,
            schema_version=event.schema_version,
            source_observations=event.source_observations,
            memory_refs=event.memory_refs,
            confidence=event.confidence,
        )
        session.add(row)
```

**Read path style:** copy the query + model reconstruction pattern from [src/sva/points/dao.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/points/dao.py:47) lines 47-65:

```python
def list_points(game_id: str) -> list[PointRecord]:
    with session_scope() as session:
        rows = session.execute(
            select(PointRow)
            .where(PointRow.game_id == game_id)
            .order_by(PointRow.point_ordinal.asc())
        ).scalars()
        return [
            PointRecord(...)
            for row in rows
        ]
```

**Closest lookup analog for cache-hit reads:** [src/sva/points/dao.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/points/dao.py:68) lines 68-87 is the existing single-record finder pattern:

```python
def find_point_for_video_ts(game_id: str, video_ts_ms: int) -> PointRecord | None:
    with session_scope() as session:
        row = session.execute(
            select(PointRow).where(
                PointRow.game_id == game_id,
                PointRow.start_video_ts_ms <= video_ts_ms,
                PointRow.end_video_ts_ms >= video_ts_ms,
            )
        ).scalar_one_or_none()
```

Use this shape for `find_cached_observation(video_id, window_id, prompt_version_hash)` or `list_cached_observations(...)`: small standalone function, `session_scope()`, `select(...)`, and conversion back into canonical Pydantic `Observation`.

### `migrations/versions/0005_phase3_observations.py` (migration, CRUD)

**Primary analogs:** `migrations/versions/0003_phase2_points.py`, `migrations/versions/0004_phase2_point_scoped_events.py`, `migrations/versions/0001_phase1_foundation.py`

**Header + create-table style:** copy from [migrations/versions/0003_phase2_points.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/migrations/versions/0003_phase2_points.py:1) lines 1-18 and lines 21-60:

```python
revision: str = "0003_phase2_points"
down_revision: str | None = "0002_phase2_sources_and_rights_acks"

def upgrade() -> None:
    op.create_table(
        "points",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        ...
        sa.Column(
            "boundary_evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_points_game_id", "points", ["game_id"], unique=False)
    op.create_index("ix_points_game_id_point_ordinal", "points", ["game_id", "point_ordinal"], unique=True)
```

**JSONB defaults + schema version style:** copy from [migrations/versions/0001_phase1_foundation.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/migrations/versions/0001_phase1_foundation.py:61) lines 61-112:

```python
op.create_table(
    "events",
    ...
    sa.Column(
        "details",
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    ),
    sa.Column(
        "schema_version",
        sa.Text(),
        nullable=False,
        server_default=sa.text("'1.0'"),
    ),
    sa.Column(
        "source_observations",
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
    ),
)
```

**Backfill-then-tighten pattern:** if the observation cache table needs staged nullability or backfill, copy [migrations/versions/0004_phase2_point_scoped_events.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/migrations/versions/0004_phase2_point_scoped_events.py:20) lines 20-37:

```python
op.add_column("events", sa.Column("point_ordinal", sa.Integer(), nullable=True))
op.add_column("events", sa.Column("in_point_ts_ms", sa.BigInteger(), nullable=True))

op.execute(
    """
    UPDATE events
    SET
        point_id = COALESCE(point_id, game_id || ':pt_001'),
        point_ordinal = COALESCE(point_ordinal, 1),
        in_point_ts_ms = COALESCE(in_point_ts_ms, video_ts_ms)
    """
)

op.alter_column("events", "point_ordinal", existing_type=sa.Integer(), nullable=False)
```

For Phase 3, the natural unique index is the exact cache triple from context: `(video_id, window_id, prompt_version_hash)`.

### `src/sva/observability/langfuse.py` (utility, request-response)

**Primary analog:** `src/sva/observability/langfuse.py`

**Trace metadata contract:** preserve [src/sva/observability/langfuse.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/observability/langfuse.py:28) lines 28-40:

```python
@dataclass(frozen=True)
class TraceContext:
    stage: str
    model: str
    video_id: str
    game_id: str
    window_id: str | None = None
    point_id: str | None = None
    point_ordinal: int | None = None
    prompt_version_hash: str | None = None
```

**Observability must never break the pipeline:** preserve [src/sva/observability/langfuse.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/observability/langfuse.py:75) lines 75-120:

```python
lf = get_langfuse()
trace = None
if lf is not None:
    try:
        trace = lf.trace(
            name=f"{stage}.call",
            metadata={
                "stage": stage,
                "model": model,
                "video_id": ctx.video_id,
                "game_id": ctx.game_id,
                "window_id": ctx.window_id,
                "point_id": ctx.point_id,
                "point_ordinal": ctx.point_ordinal,
            },
            tags=[stage, model, f"video:{ctx.video_id}"],
        )
    except Exception as exc:
        logger.warning("Langfuse trace create failed: %s", exc)
        trace = None

...

try:
    from sva.observability.cost import record_job_cost
    record_job_cost(ctx.game_id, cost_usd)
except Exception as exc:
    logger.warning("record_job_cost failed: %s", exc)
```

Phase 3 should extend this existing metadata dictionary to include `prompt_version_hash`; do not introduce a separate tracing path.

### `src/sva/pipeline.py` (service, batch)

**Primary analog:** `src/sva/pipeline.py`

**Persist-first stage ordering already exists for points** in [src/sva/pipeline.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/pipeline.py:128) lines 128-132:

```python
point_candidates = _build_point_boundary_candidates(ing)
points = detect_points(ing.game_id, point_candidates)
if points:
    insert_points(points)
persisted_points = list_points(ing.game_id)
```

**Per-window insertion point for persisted observations** is [src/sva/pipeline.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/pipeline.py:137) lines 137-160:

```python
for start_ms, end_ms in ing.windows:
    owning_point = _resolve_window_point(persisted_points, start_ms, end_ms)
    if owning_point is None:
        continue
    window = PerceiveWindow(...)
    window_ctx = TraceContext(...)
    try:
        obs = run_window(window_ctx, window, perceiver=perceiver)
        observations.append(obs)
        observations_by_point[owning_point.point_id].append(obs)
    except Exception as exc:
        logger.exception("perceive failed for window %s: %s", window.window_id, exc)
```

If Phase 3 persists observations inside `run_window`, the pipeline can stay unchanged. If persistence happens outside `run_window`, insert it immediately after `obs = run_window(...)` and before either append.

**Downstream contract to preserve:** [src/sva/pipeline.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/pipeline.py:164) lines 164-189 consumes point-grouped observations and only then runs interpret and event persistence:

```python
for point_id, point_observations in observations_by_point.items():
    if not point_observations:
        continue
    ...
    event = run_point(interpret_ctx, point_observations, interpreter=interpreter, retrieved=retrieved)
    scoped_event = _apply_point_scope(...)
    insert_event(scoped_event)
```

This is the existing persisted-stage-output seam: perception output must exist before interpret starts.

### `tests/test_perceive_adapter.py` (test, request-response)

**Primary analog:** `tests/test_perceive_adapter.py`

**DB-gated integration test style:** copy [tests/test_perceive_adapter.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/tests/test_perceive_adapter.py:9) lines 9-21:

```python
def _db_reachable() -> bool:
    try:
        from sva.db import get_engine
        with get_engine().connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

@pytest.mark.skipif(not _db_reachable(), reason="Postgres unreachable")
```

**Seed jobs row and assert cost side effect:** copy [tests/test_perceive_adapter.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/tests/test_perceive_adapter.py:26) lines 26-57:

```python
game_id = "test_perceive_game_1"
with get_engine().begin() as conn:
    conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})
    conn.execute(
        text("INSERT INTO jobs (game_id, video_id, status) VALUES (:g, :v, 'streaming')"),
        {"g": game_id, "v": "vid_test"},
    )

obs = GeminiPerceiver().perceive(ctx, window)
assert obs.schema_version == "1.0"
assert obs.model.provider == "gemini"

with get_engine().connect() as conn:
    cost = conn.execute(
        text("SELECT cost_usd FROM jobs WHERE game_id = :g"),
        {"g": game_id},
    ).scalar()
assert cost is not None
assert float(cost) > 0
```

Use this exact pattern for any real-adapter or real-cache integration test that touches Postgres.

### `tests/test_swap_safe_contract.py` (test, request-response)

**Primary analog:** `tests/test_swap_safe_contract.py`

**Dummy adapter pattern:** preserve [tests/test_swap_safe_contract.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/tests/test_swap_safe_contract.py:38) lines 38-64:

```python
class DummyPerceiver:
    model_id = "dummy-vlm-v0"
    provider = "dummy"

    def perceive(self, ctx: TraceContext, window: PerceiveWindow) -> Observation:
        return Observation(
            observation_id=f"obs_dummy_{window.window_id}",
            window_id=window.window_id,
            video_id=window.video_id,
            video_ts_start_ms=window.video_ts_start_ms,
            video_ts_end_ms=window.video_ts_end_ms,
            observation_ts_ms=window.video_ts_start_ms,
            ...
            model=ModelMetadata(provider="dummy", model_id="dummy-vlm-v0", version="test"),
            confidence_overall=0.42,
        )
```

**Runner-level swap-safe assertion:** preserve [tests/test_swap_safe_contract.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/tests/test_swap_safe_contract.py:74) lines 74-93:

```python
obs = run_window(ctx, window, perceiver=DummyPerceiver())
assert obs.model.provider == "dummy"
assert obs.confidence_overall == 0.42
assert obs.schema_version == "1.0"
```

Phase 3 cache coverage should extend this test style, not replace it: cache hit and live Gemini path must both satisfy the same `run_window(...) -> Observation` contract.

### `tests/test_point_scoped_pipeline.py` (test, batch)

**Primary analog:** `tests/test_point_scoped_pipeline.py`

**Monkeypatch orchestration seam pattern:** copy [tests/test_point_scoped_pipeline.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/tests/test_point_scoped_pipeline.py:40) lines 40-125:

```python
order: list[str] = []

def fake_ingest_clip(source_path, game_id=None):
    order.append("ingest")
    return IngestResult(...)

def fake_detect_points(game_id, candidates):
    order.append("detect")
    return points

def fake_insert_points(detected_points):
    order.append("persist_points")

def fake_run_window(ctx, window, perceiver=None):
    order.append(f"perceive:{ctx.point_id}")
    return Observation(...)

def fake_run_point(ctx, observations, interpreter=None, retrieved=None):
    order.append(f"interpret:{ctx.point_id}")
    return Event(...)

monkeypatch.setattr("sva.pipeline.run_window", fake_run_window)
monkeypatch.setattr("sva.pipeline.run_point", fake_run_point)
monkeypatch.setattr("sva.pipeline.insert_event", fake_insert_event)
```

**Ordering assertions to reuse:** preserve [tests/test_point_scoped_pipeline.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/tests/test_point_scoped_pipeline.py:128) lines 128-138:

```python
assert result.events_inserted == 2
assert result.observations == 2
assert order.index("detect") < order.index("perceive:game_test:pt_001")
assert order.index("detect") < order.index("perceive:game_test:pt_002")
assert order.index("interpret:game_test:pt_001") < order.index("persist_event:game_test:pt_001")
assert order.index("interpret:game_test:pt_002") < order.index("persist_event:game_test:pt_002")
```

Use this exact pattern for the new stage-order invariant: `persist_observation` must happen before `interpret:*`, and a cache hit must produce no `gemini_call:*` marker.

### `tests/test_observations_dao.py` (test, CRUD)

**Primary analog:** `tests/test_observability.py`

**DB-gated write/read test style:** copy [tests/test_observability.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/tests/test_observability.py:44) lines 44-65:

```python
@pytest.mark.skipif(not _db_reachable(), reason="Postgres unreachable; start `docker compose up -d db`")
def test_record_job_cost_aggregates_per_game():
    from sva.db import get_engine
    ...
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})

    record_job_cost(game_id, Decimal("0.001234"))
    record_job_cost(game_id, Decimal("0.002000"))

    with get_engine().connect() as conn:
        total = conn.execute(
            text("SELECT cost_usd FROM jobs WHERE game_id = :g"),
            {"g": game_id},
        ).scalar()
```

**Prompt-version-hash fixture pattern:** reuse [tests/test_observability.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/tests/test_observability.py:91) lines 91-126 when testing the cache-key triple:

```python
hash_a = hashlib.sha256(prompt_a.encode()).hexdigest()[:12]
hash_b = hashlib.sha256(prompt_b.encode()).hexdigest()[:12]

ctx_a = TraceContext(..., prompt_version_hash=hash_a)
ctx_b = TraceContext(..., prompt_version_hash=hash_b)

assert len(ctx_a.prompt_version_hash) == 12
assert ctx_a.prompt_version_hash != ctx_b.prompt_version_hash
```

Use this exact hashing pattern in observation-cache tests so `(video_id, window_id, prompt_version_hash)` behavior is proven, not hand-waved.

## Shared Patterns

### Transaction Scope
**Source:** [src/sva/db.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/db.py:30)
**Apply to:** all new DAO functions and any direct SQL helper

```python
@contextmanager
def session_scope() -> Iterator[Session]:
    factory = _get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

### Versioned Pydantic Boundary
**Source:** [src/sva/perceive/adapters/base.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/perceive/adapters/base.py:13), [src/sva/models.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/models.py:80)
**Apply to:** adapter return values, DAO reconstruction, cache-hit return path

```python
class PerceiveWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    window_id: str
    video_id: str
    video_ts_start_ms: int = Field(ge=0)
    video_ts_end_ms: int = Field(ge=0)
    transcoded_path: str

class Perceiver(Protocol):
    def perceive(self, ctx: TraceContext, window: PerceiveWindow) -> Observation: ...
```

```python
class Observation(BaseModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    observation_id: str
    window_id: str
    video_id: str
    ...
    model: ModelMetadata
    confidence_overall: float = Field(ge=0.0, le=1.0)
    raw_response_ref: str | None = None
```

### Cost Recording
**Source:** [src/sva/observability/cost.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/src/sva/observability/cost.py:39)
**Apply to:** live Gemini calls, not cache hits

```python
def estimate_gemini_cost(
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    model: str = "gemini-2.5-flash",
) -> Decimal:
    rates = _GEMINI_RATES.get(model, _GEMINI_RATES["gemini-2.5-flash"])
    fresh_input = max(input_tokens - cached_input_tokens, 0)
    return (
        Decimal(fresh_input) * rates["input"]
        + Decimal(cached_input_tokens) * rates["cache_read"]
        + Decimal(output_tokens) * rates["output"]
    )
```

```python
def record_job_cost(game_id: str, delta_usd: Decimal) -> None:
    with session_scope() as session:
        result = session.execute(
            text(
                "UPDATE jobs SET cost_usd = cost_usd + :delta, updated_at = now() "
                "WHERE game_id = :gid"
            ),
            {"delta": delta_usd, "gid": game_id},
        )
        if result.rowcount == 0:
            session.execute(
                text(
                    "INSERT INTO jobs (game_id, video_id, status, cost_usd) "
                    "VALUES (:gid, :vid, 'streaming', :delta)"
                ),
                {"gid": game_id, "vid": f"vid_missing_{game_id}", "delta": delta_usd},
            )
```

### DB-Gated Integration Tests
**Source:** [tests/test_perceive_adapter.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/tests/test_perceive_adapter.py:20), [tests/test_observability.py](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/tests/test_observability.py:44)
**Apply to:** DAO integration tests, real-adapter tests, migration-sensitive tests

```python
@pytest.mark.skipif(not _db_reachable(), reason="Postgres unreachable")
```

## No Exact Analog Found

| File / Concern | Role | Data Flow | Reason |
|---|---|---|---|
| `src/sva/perceive/dao.py` cache-hit query by `(video_id, window_id, prompt_version_hash)` | service | CRUD | No existing table currently stores first-class observations, so there is no exact persistent-cache lookup example. Build from `points/dao.py` read patterns plus `runner.py` seam. |
| `src/sva/perceive/runner.py` cache lookup before expensive Gemini work | service | request-response | There is no current persistent short-circuit path before a model call. The exact insertion seam exists, but the cache branch itself is new. |
| Gemini retry/backoff inside `_call_gemini` | service | request-response | No current adapter implements bounded exponential retry. Preserve the `_call_*` + `observe_call` structure and add retry logic inside that private function. |

## Metadata

**Analog search scope:** `src/sva/perceive`, `src/sva/interpret`, `src/sva/observability`, `src/sva/points`, `src/sva`, `tests`, `migrations/versions`
**Files scanned:** 20
**Pattern extraction date:** 2026-04-23
