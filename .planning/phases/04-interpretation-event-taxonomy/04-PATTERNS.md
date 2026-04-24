# Phase 04: Interpretation & Event Taxonomy - Pattern Map

**Mapped:** 2026-04-24
**Files analyzed:** 16 likely Phase 4 files
**Analogs found:** 15 / 16

New-file names below are inferred from `04-CONTEXT.md` plus current repo gaps. If the planner chooses equivalent names, keep the same analogs and excerpts.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/sva/interpret/adapters/base.py` | provider | request-response | `src/sva/perceive/adapters/base.py` | exact |
| `src/sva/interpret/adapters/claude.py` | provider | request-response | `src/sva/perceive/adapters/gemini.py` | exact |
| `src/sva/interpret/runner.py` | service | request-response | `src/sva/perceive/runner.py` | exact |
| `src/sva/models.py` | model | transform | `src/sva/models.py` | self |
| `src/sva/events_dao.py` | service | CRUD | `src/sva/observations_dao.py` | exact |
| `src/sva/pipeline.py` | service | batch | `src/sva/pipeline.py` | self |
| `src/sva/interpret/rules.py` | utility | file-I/O | `src/sva/ingest/sources.py` | role-match |
| `src/sva/interpret/validator.py` | utility | transform | `src/sva/ingest/sources.py` | role-match |
| `rulebook/usau_2024_2025.yaml` | config | file-I/O | none in repo | none |
| `migrations/versions/0006_phase4_interpretation_audit_fields.py` | migration | CRUD | `migrations/versions/0005_phase3_observations.py` | exact |
| `tests/test_interpret_adapter.py` | test | request-response | `tests/test_perceive_adapter.py` | exact |
| `tests/test_point_scoped_pipeline.py` | test | batch | `tests/test_point_scoped_pipeline.py` | self |
| `tests/test_models.py` | test | transform | `tests/test_models.py` | self |
| `tests/test_events_dao.py` | test | CRUD | `tests/test_observations_dao.py` | exact |
| `tests/test_swap_safe_contract.py` | test | request-response | `tests/test_swap_safe_contract.py` | self |
| `tests/test_interpret_validator.py` | test | transform | `tests/test_ingest_sources.py` | role-match |

## Pattern Assignments

### `src/sva/interpret/adapters/base.py` (provider, request-response)

**Analog:** `src/sva/perceive/adapters/base.py`

**Imports + protocol shape** ([src/sva/perceive/adapters/base.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/perceive/adapters/base.py:5)):
```python
from typing import Protocol

from sva.models import Observation
from sva.observability import TraceContext


class Perceiver(Protocol):
    def perceive(self, ctx: TraceContext, window: PerceiveWindow) -> Observation: ...
```

**What to copy**
- Keep `Protocol`-based swap-safe duck typing.
- Keep a tiny file with only imports, contract types, and `__all__`.
- Phase 4 change is only the return type and argument contract: `interpret(...) -> list[Event]`.

---

### `src/sva/interpret/adapters/claude.py` (provider, request-response)

**Primary analog:** `src/sva/perceive/adapters/gemini.py`

**Keep current provider constants + wrapper shape** ([src/sva/interpret/adapters/claude.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/interpret/adapters/claude.py:16)):
```python
_MODEL_ID = "claude-sonnet-4-5"
_VERSION = "phase1-stub-v0"


class ClaudeInterpreter:
    model_id: str = _MODEL_ID
    provider: str = "anthropic"
```

**Prompt hash + decorated call pattern** ([src/sva/perceive/adapters/gemini.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/perceive/adapters/gemini.py:124)):
```python
@observe_call(stage="perceive", model=_MODEL_ID)
def _call_gemini(
    ctx: TraceContext,
    window: PerceiveWindow,
) -> tuple[Observation, Decimal, int, int, TraceContext]:
    prompt = _build_prompt(window)
    prompt_hash = prompt_version_hash(prompt)
```

**Updated trace context on success** ([src/sva/perceive/adapters/gemini.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/perceive/adapters/gemini.py:157)):
```python
updated_ctx = TraceContext(
    stage=ctx.stage,
    model=ctx.model,
    video_id=ctx.video_id,
    game_id=ctx.game_id,
    window_id=ctx.window_id,
    point_id=ctx.point_id,
    point_ordinal=ctx.point_ordinal,
    prompt_version_hash=prompt_hash,
    latency_ms=int((time.monotonic() - started) * 1000),
    retry_count=retry_count,
    terminal_status="success",
)
```

**Retry + fail-through observability pattern** ([src/sva/perceive/adapters/gemini.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/perceive/adapters/gemini.py:173)):
```python
except Exception as exc:
    retry_count = attempt + 1
    if attempt >= _MAX_RETRIES or not _is_retryable_error(exc):
        updated_ctx = TraceContext(
            stage=ctx.stage,
            model=ctx.model,
            video_id=ctx.video_id,
            game_id=ctx.game_id,
            window_id=ctx.window_id,
            point_id=ctx.point_id,
            point_ordinal=ctx.point_ordinal,
            prompt_version_hash=prompt_hash,
            latency_ms=int((time.monotonic() - started) * 1000),
            retry_count=retry_count,
            terminal_status="retry_exhausted" if _is_retryable_error(exc) else "error",
        )
        exc.updated_ctx = updated_ctx
        raise
```

**Public wrapper pattern** ([src/sva/perceive/adapters/gemini.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/perceive/adapters/gemini.py:203)):
```python
def prompt_hash_for(self, window: PerceiveWindow) -> str:
    return prompt_version_hash(_build_prompt(window))

def perceive(self, ctx: TraceContext, window: PerceiveWindow) -> Observation:
    prompt_hash = self.prompt_hash_for(window)
    enriched = TraceContext(
        stage="perceive",
        model=_MODEL_ID,
        video_id=ctx.video_id,
        game_id=ctx.game_id,
        window_id=window.window_id,
        point_id=ctx.point_id,
        point_ordinal=ctx.point_ordinal,
        prompt_version_hash=prompt_hash,
    )
    return _call_gemini(enriched, window)
```

**Phase 4 guidance**
- Mirror the Gemini adapter structure: prompt builder, SDK client helper, parse helper, decorated `_call_*`, thin public wrapper.
- Replace single `Event` output with `list[Event]` but keep the `observe_call(...)` tuple contract intact.
- Pull Anthropic credentials from the shared singleton settings surface in [src/sva/config.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/config.py:12).
- Preserve `source_observations`, `rule_refs`, `memory_refs`, and explicit prompt hash propagation.

---

### `src/sva/interpret/runner.py` (service, request-response)

**Analog:** `src/sva/perceive/runner.py`

**Default swap point** ([src/sva/perceive/runner.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/perceive/runner.py:19)):
```python
def make_default_perceiver() -> Perceiver:
    return GeminiPerceiver()
```

**Thin orchestrator shape** ([src/sva/perceive/runner.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/perceive/runner.py:69)):
```python
def run_window(
    ctx: TraceContext,
    window: PerceiveWindow,
    perceiver: Perceiver | None = None,
    on_cache_miss: CacheMissHandler | None = None,
) -> Observation:
    p = perceiver or make_default_perceiver()
```

**What to copy**
- Keep the runner tiny and provider-agnostic.
- Keep `make_default_interpreter()` as the only backend swap point.
- Add optional validator application here only if it stays orchestration-thin; otherwise keep validator in pipeline.

---

### `src/sva/models.py` (model, transform)

**Analog:** current `src/sva/models.py`

**Closed enum + provider-neutral aliases** ([src/sva/models.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/models.py:19)):
```python
EventType = Literal[
    "possession_start",
    "possession_end",
    "completion",
    "turnover",
    "goal",
    "point_end",
    "unknown",
]
Team = Literal["dark", "light", "none", "unknown"]
```

**Canonical event contract pattern** ([src/sva/models.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/models.py:105)):
```python
class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    event_id: str
    game_id: str
    point_id: str
    point_ordinal: int = Field(ge=1)
    video_ts_ms: int = Field(ge=0)
    in_point_ts_ms: int = Field(ge=0)
    type: EventType
    team: Team = "unknown"
    details: dict[str, Any] = Field(default_factory=dict)
    source_observations: list[str] = Field(default_factory=list)
    rule_refs: list[str] = Field(default_factory=list)
    memory_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    warnings: list[str] = Field(default_factory=list)
    model: ModelMetadata
```

**Validation test pattern to preserve** ([tests/test_models.py](/Users/lauluzhong/Documents/Sports Video Analytics/tests/test_models.py:40)):
```python
with pytest.raises(ValidationError):
    Event(
        event_id="e1",
        game_id="g1",
        point_id="g1:pt_001",
        point_ordinal=1,
        video_ts_ms=0,
        in_point_ts_ms=0,
        type="not_a_real_event",
        model=ModelMetadata(provider="anthropic", model_id="claude-sonnet-4-5", version="v1"),
    )
```

**Phase 4 guidance**
- Extend the existing closed contract instead of introducing provider-shaped response models into the rest of the repo.
- Keep new taxonomy bits in `details` unless they are clearly canonical enough for top-level fields.
- If prompt-version identity becomes a first-class field, define it here with the same `extra="forbid"` and default-safe style.

---

### `src/sva/events_dao.py` (service, CRUD)

**Primary analog:** `src/sva/observations_dao.py`

**ORM column pattern** ([src/sva/observations_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/observations_dao.py:13)):
```python
class ObservationRow(Base):
    __tablename__ = "observations"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    observation_id = Column(Text, nullable=False, unique=True)
    game_id = Column(Text, ForeignKey("jobs.game_id", ondelete="CASCADE"), nullable=False, index=True)
    point_id = Column(Text, nullable=False, index=True)
```

**Bulk persistence pattern** ([src/sva/observations_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/observations_dao.py:37)):
```python
def insert_observations(
    *,
    game_id: str,
    point_id: str,
    point_ordinal: int,
    prompt_version_hash: str,
    observations: list[Observation],
    cache_hit: bool = False,
) -> None:
    with session_scope() as session:
        session.add_all([...])
```

**Ordered lookup pattern already present** ([src/sva/events_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/events_dao.py:56)):
```python
def list_event_rows_for_point(game_id: str, point_id: str) -> list[EventRow]:
    with session_scope() as session:
        return list(
            session.execute(
                select(EventRow)
                .where(EventRow.game_id == game_id, EventRow.point_id == point_id)
                .order_by(EventRow.video_ts_ms.asc())
            ).scalars()
        )
```

**Phase 4 guidance**
- Copy the `observations_dao` approach if Phase 4 adds `insert_events(events: list[Event])`.
- The current file is missing persistence for `rule_refs`, `warnings`, and any explicit prompt-version storage; Phase 4 likely needs both DAO changes and a migration.
- Keep event ordering by `video_ts_ms`.

---

### `src/sva/pipeline.py` (service, batch)

**Analog:** current `src/sva/pipeline.py`

**Point-grouped fanout pattern** ([src/sva/pipeline.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/pipeline.py:137)):
```python
observations: list[Observation] = []
observations_by_point: dict[str, list[Observation]] = defaultdict(list)
points_by_id = {point.point_id: point for point in persisted_points}
for start_ms, end_ms in ing.windows:
    owning_point = _resolve_window_point(persisted_points, start_ms, end_ms)
    if owning_point is None:
        continue
```

**Per-point interpretation seam** ([src/sva/pipeline.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/pipeline.py:183)):
```python
for point_id, point_observations in observations_by_point.items():
    if not point_observations:
        continue
    point = points_by_id[point_id]
    retrieved = asyncio.run(
        retriever.retrieve(
            RetrievalQuery(event_candidate_type="unknown", context_text=""),
        )
    )
    interpret_ctx = TraceContext(
        stage="interpret",
        model=getattr(interpreter, "model_id", "unknown"),
        video_id=ing.video_id,
        game_id=ing.game_id,
        point_id=point.point_id,
        point_ordinal=point.point_ordinal,
    )
    event = run_point(interpret_ctx, point_observations, interpreter=interpreter, retrieved=retrieved)
```

**Immutable event adjustment pattern** ([src/sva/pipeline.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/pipeline.py:94)):
```python
return event.model_copy(
    update={
        "point_id": point.point_id,
        "point_ordinal": point.point_ordinal,
        "video_ts_ms": absolute_ts_ms,
        "in_point_ts_ms": in_point_ts_ms,
    }
)
```

**Phase 4 guidance**
- Keep retrieval once per point, not once per emitted event.
- Replace the single-event path with a loop over `list[Event]`, then scope/validate/persist each event.
- Reuse `model_copy(update=...)` instead of mutating Pydantic instances in place.

---

### `src/sva/interpret/rules.py` (utility, file-I/O)

**Closest analog:** `src/sva/ingest/sources.py`

**Constants + domain-specific exceptions** ([src/sva/ingest/sources.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/ingest/sources.py:16)):
```python
YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
}

class SourcePolicyError(ValueError):
    """Base class for rejected source inputs."""
```

**Pure validation function style** ([src/sva/ingest/sources.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/ingest/sources.py:87)):
```python
def validate_remote_source(source: RemoteUrlSource) -> RemoteUrlSource:
    if not source.ack_rights:
        raise RightsAckRequiredError(...)
    if not source.caller_id.strip():
        raise SourcePolicyError(...)
    host = _normalized_host(source.url)
    if host not in ALLOWED_PUBLIC_VIDEO_HOSTS:
        raise UnsupportedSourceError(...)
    return source
```

**Phase 4 guidance**
- Keep rule loading as deterministic helpers plus small typed errors.
- Use `Path`/`lru_cache` style loading if the rulebook file is parsed repeatedly.
- If this becomes a package instead of one module, keep each file small and pure like `ingest/sources.py`.

---

### `src/sva/interpret/validator.py` (utility, transform)

**Closest analogs:** `src/sva/pipeline.py`, `src/sva/ingest/sampler.py`

**Pure guard function pattern** ([src/sva/ingest/sampler.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/ingest/sampler.py:6)):
```python
def validate_sampling_fps(fps: int) -> int:
    if fps < 1 or fps > 3:
        raise ValueError("fps must be within the v1 envelope: 1 <= fps <= 3")
    return fps
```

**Immutable correction pattern** ([src/sva/pipeline.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/pipeline.py:94)):
```python
return event.model_copy(
    update={
        "point_id": point.point_id,
        "point_ordinal": point.point_ordinal,
        "video_ts_ms": absolute_ts_ms,
        "in_point_ts_ms": in_point_ts_ms,
    }
)
```

**Phase 4 guidance**
- Make the validator a pure function over `list[Event]` and `list[Observation]`.
- Prefer annotating/downgrading via `warnings`, `confidence`, or `details` updates over dropping events.
- Reserve exceptions for impossible internal invariants, not normal model uncertainty.

---

### `rulebook/usau_2024_2025.yaml` (config, file-I/O)

**Analog:** none in repo

**Phase 4 guidance**
- Keep it human-editable and versioned in-repo.
- Prefer stable keys that can be copied into `Event.rule_refs`.
- Planner should use the repo's existing flat, explicit style rather than inventing a framework around this file.

---

### `migrations/versions/0006_phase4_interpretation_audit_fields.py` (migration, CRUD)

**Primary analogs:** `migrations/versions/0005_phase3_observations.py`, `migrations/versions/0004_phase2_point_scoped_events.py`

**Revision header pattern** ([migrations/versions/0005_phase3_observations.py](/Users/lauluzhong/Documents/Sports Video Analytics/migrations/versions/0005_phase3_observations.py:1)):
```python
revision: str = "0005_phase3_observations"
down_revision: str | None = "0004_phase2_point_scoped_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
```

**Create/add column + index pattern** ([migrations/versions/0005_phase3_observations.py](/Users/lauluzhong/Documents/Sports Video Analytics/migrations/versions/0005_phase3_observations.py:21)):
```python
op.create_table(
    "observations",
    sa.Column("prompt_version_hash", sa.Text(), nullable=False),
    sa.Column(
        "payload",
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    ),
)
op.create_index("ix_observations_cache_key", "observations", [...], unique=False)
```

**Backfill then enforce non-null pattern** ([migrations/versions/0004_phase2_point_scoped_events.py](/Users/lauluzhong/Documents/Sports Video Analytics/migrations/versions/0004_phase2_point_scoped_events.py:20)):
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

**Phase 4 guidance**
- If new event audit columns are required, follow the `add nullable -> backfill -> alter non-null -> index` pattern.
- Update migration smoke coverage only if Phase 4 introduces materially new table/column guarantees.

---

### `tests/test_interpret_adapter.py` (test, request-response)

**Primary analog:** `tests/test_perceive_adapter.py`

**DB-gated integration setup pattern** ([tests/test_interpret_adapter.py](/Users/lauluzhong/Documents/Sports Video Analytics/tests/test_interpret_adapter.py:41)):
```python
@pytest.mark.skipif(not _db_reachable(), reason="Postgres unreachable")
def test_claude_interpreter_emits_valid_event():
    from sva.db import get_engine
    from sva.interpret import ClaudeInterpreter
```

**Monkeypatched SDK test pattern** ([tests/test_perceive_adapter.py](/Users/lauluzhong/Documents/Sports Video Analytics/tests/test_perceive_adapter.py:65)):
```python
fake_client = SimpleNamespace(files=FakeFiles(), models=FakeModels())
monkeypatch.setattr("sva.perceive.adapters.gemini._get_client", lambda: fake_client)
monkeypatch.setattr("sva.observability.langfuse.get_langfuse", lambda: None)
monkeypatch.setattr("sva.observability.cost.record_job_cost", lambda game_id, delta_usd: None)
```

**Retry-path test pattern** ([tests/test_perceive_adapter.py](/Users/lauluzhong/Documents/Sports Video Analytics/tests/test_perceive_adapter.py:145)):
```python
class RetryableError(RuntimeError):
    status_code = 429

with pytest.raises(RetryableError):
    GeminiPerceiver().perceive(ctx, window)
```

**Phase 4 guidance**
- Keep one DB-gated smoke test and add pure monkeypatched unit tests for prompt construction, parsed output normalization, and retry/fail-open observability.
- Update assertions from single `Event` to ordered `list[Event]`.

---

### `tests/test_point_scoped_pipeline.py` (test, batch)

**Analog:** current `tests/test_point_scoped_pipeline.py`

**Monkeypatch-heavy orchestration pattern** ([tests/test_point_scoped_pipeline.py](/Users/lauluzhong/Documents/Sports Video Analytics/tests/test_point_scoped_pipeline.py:42)):
```python
monkeypatch.setattr("sva.pipeline.ingest_clip", fake_ingest_clip)
monkeypatch.setattr("sva.pipeline.detect_points", fake_detect_points)
monkeypatch.setattr("sva.pipeline.make_default_perceiver", lambda: DummyPerceiver())
monkeypatch.setattr("sva.pipeline.run_point", fake_run_point)
monkeypatch.setattr("sva.pipeline.insert_event", fake_insert_event)
```

**Ordered side-effect assertions** ([tests/test_point_scoped_pipeline.py](/Users/lauluzhong/Documents/Sports Video Analytics/tests/test_point_scoped_pipeline.py:153)):
```python
assert order.index("detect") < order.index("perceive:game_test:pt_001")
assert order.index("persist_observation:game_test:pt_001") < order.index("interpret:game_test:pt_001")
assert order.index("interpret:game_test:pt_001") < order.index("persist_event:game_test:pt_001")
```

**Phase 4 guidance**
- Keep this test as the main proof that point detection still happens before interpretation.
- Change the fake interpreter to return `list[Event]` and assert per-point fanout order and persistence count.

---

### `tests/test_models.py` (test, transform)

**Analog:** current `tests/test_models.py`

**Closed-enum guard** ([tests/test_models.py](/Users/lauluzhong/Documents/Sports Video Analytics/tests/test_models.py:40)):
```python
with pytest.raises(ValidationError):
    Event(..., type="not_a_real_event", ...)
```

**No vendor leakage pattern** ([tests/test_models.py](/Users/lauluzhong/Documents/Sports Video Analytics/tests/test_models.py:93)):
```python
for cls in (Observation, Event, MemoryRecord):
    for name in cls.model_fields:
        lowered = name.lower()
        for f in forbidden:
            assert f not in lowered
```

**Phase 4 guidance**
- Add new taxonomy and prompt-version assertions here first.
- Keep this file focused on contract safety, not pipeline behavior.

---

### `tests/test_events_dao.py` (test, CRUD)

**Primary analog:** `tests/test_observations_dao.py`

**Migrated DB fixture pattern** ([tests/test_observations_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/tests/test_observations_dao.py:25)):
```python
@pytest.fixture(scope="module")
def migrated_db():
    if not _db_reachable():
        pytest.skip("Postgres not reachable; start with `docker compose up -d db`")
    env = os.environ.copy()
    subprocess.run(["alembic", "upgrade", "head"], check=True, env=env)
    yield
```

**Insert/query assertion pattern** ([tests/test_events_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/tests/test_events_dao.py:51)):
```python
insert_event(Event(...))
point_one_rows = list_event_rows_for_point(game_id, f"{game_id}:pt_001")
assert len(point_one_rows) == 1
assert point_one_rows[0].point_id == f"{game_id}:pt_001"
assert point_one_rows[0].point_ordinal == 1
assert int(point_one_rows[0].in_point_ts_ms) == 1000
```

**Phase 4 guidance**
- Add assertions for every new persisted audit field, especially `rule_refs`.
- If Phase 4 adds bulk insert, mirror the list-order assertions from `tests/test_observations_dao.py`.

---

### `tests/test_swap_safe_contract.py` (test, request-response)

**Analog:** current `tests/test_swap_safe_contract.py`

**Dummy adapter substitution pattern** ([tests/test_swap_safe_contract.py](/Users/lauluzhong/Documents/Sports Video Analytics/tests/test_swap_safe_contract.py:38)):
```python
class DummyPerceiver:
    model_id = "dummy-vlm-v0"
    provider = "dummy"

    def perceive(self, ctx: TraceContext, window: PerceiveWindow) -> Observation:
        return Observation(...)
```

**Call through runner, not concrete class checks** ([tests/test_swap_safe_contract.py](/Users/lauluzhong/Documents/Sports Video Analytics/tests/test_swap_safe_contract.py:67)):
```python
p: Perceiver = DummyPerceiver()
assert hasattr(p, "perceive")

obs = run_window(ctx, window, perceiver=DummyPerceiver())
assert obs.model.provider == "dummy"
```

**Phase 4 guidance**
- Mirror this style for the interpreter seam: dummy interpreter returning `list[Event]`, tested via `run_point(...)`.
- Keep the test structural and backend-agnostic.

---

### `tests/test_interpret_validator.py` (test, transform)

**Closest analog:** `tests/test_ingest_sources.py`

**Explicit example-case style** ([tests/test_ingest_sources.py](/Users/lauluzhong/Documents/Sports Video Analytics/tests/test_ingest_sources.py:22)):
```python
def test_validate_remote_source_accepts_youtube_and_ufa():
    assert validate_remote_source(RemoteUrlSource(...)).url == "https://www.youtube.com/watch?v=abc123"
```

**Reject/guard style** ([tests/test_ingest_sources.py](/Users/lauluzhong/Documents/Sports Video Analytics/tests/test_ingest_sources.py:39)):
```python
with pytest.raises(RightsAckRequiredError):
    validate_remote_source(RemoteUrlSource(...))
```

**Phase 4 guidance**
- Write concrete sequence fixtures: impossible possession flip, goal without offensive possession, point_end without goal, event with empty `source_observations`.
- Prefer asserting downgraded confidence and appended warnings over hard failure, matching D-06.

## Shared Patterns

### Observability
**Sources:** [src/sva/observability/langfuse.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/observability/langfuse.py:64), [src/sva/perceive/adapters/gemini.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/perceive/adapters/gemini.py:124)

Apply to all VLM/LLM adapters:
```python
@observe_call(stage="perceive", model=_MODEL_ID)
def _call_gemini(...) -> tuple[Observation, Decimal, int, int, TraceContext]:
    ...
    return (observation, cost, input_tokens, output_tokens, updated_ctx)
```

- Decorated internal call returns a 5-tuple.
- Public adapter method returns only the model object because `observe_call` strips the tuple.
- Failures should attach `exc.updated_ctx` instead of bypassing observability.

### Prompt Version Identity
**Sources:** [src/sva/observability/langfuse.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/observability/langfuse.py:165), [src/sva/perceive/adapters/gemini.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/perceive/adapters/gemini.py:203)

Apply to the interpretation prompt path:
```python
def prompt_hash_for(self, window: PerceiveWindow) -> str:
    return prompt_version_hash(_build_prompt(window))
```

- Compute prompt hashes from the full prompt string.
- Thread the hash through `TraceContext` and any persistence layer chosen for replayability.

### Pure Validation Helpers
**Sources:** [src/sva/ingest/sources.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/ingest/sources.py:32), [src/sva/pipeline.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/pipeline.py:94)

Apply to rules loading and post-LLM validation:
```python
class SourcePolicyError(ValueError):
    """Base class for rejected source inputs."""

return event.model_copy(update={...})
```

- Keep deterministic validation as pure helpers plus typed exceptions where needed.
- Prefer immutable `model_copy(update=...)` adjustments for canonical objects.

### DB-Gated Persistence Tests
**Sources:** [tests/test_observations_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/tests/test_observations_dao.py:25), [tests/test_events_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/tests/test_events_dao.py:34)

Apply to DAO and migration verification:
```python
@pytest.fixture(scope="module")
def migrated_db():
    ...
    subprocess.run(["alembic", "upgrade", "head"], check=True, env=env)
    yield
```

- Keep DB availability checks at the top of integration tests.
- Clean up inserted rows inside the test module.

## No Analog Found

Files with no close repo analog:

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `rulebook/usau_2024_2025.yaml` | config | file-I/O | Repo has no human-edited domain data directory yet; this is a new pattern for Sports Video Analytics. |

## Metadata

**Analog search scope:** `src/sva/interpret/`, `src/sva/perceive/`, `src/sva/observability/`, `src/sva/ingest/`, `src/sva/`, `tests/`, `migrations/versions/`, `.planning/phases/04-interpretation-event-taxonomy/`

**Files scanned:** 21

**Key patterns identified**
- All provider adapters use a decorated internal call plus a thin public wrapper that enriches `TraceContext`.
- Swap-safe seams are `Protocol`-based with a single default-factory swap point.
- Deterministic repo helpers stay small, pure, and explicit; tests use concrete example cases rather than abstractions.
- DAO and migration work follows SQLAlchemy ORM rows plus DB-gated pytest fixtures and `alembic upgrade head`.

**File created:** `.planning/phases/04-interpretation-event-taxonomy/04-PATTERNS.md`
