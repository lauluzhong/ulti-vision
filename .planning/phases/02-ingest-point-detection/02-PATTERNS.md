# Phase 02: ingest-point-detection - Pattern Map

**Mapped:** 2026-04-23
**Files analyzed:** 16 likely new/modified files
**Analogs found:** 15 / 16

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `pyproject.toml` | config | transform | `pyproject.toml` | exact |
| `src/sva/config.py` | config | transform | `src/sva/config.py` | exact |
| `src/sva/ingest/ingest.py` | service | file-I/O | `src/sva/ingest/ingest.py` | exact |
| `src/sva/ingest/sources.py` | service | file-I/O | `src/sva/ingest/ingest.py` | role-match |
| `src/sva/api/app.py` | route | request-response | `src/sva/cli.py` | partial |
| `src/sva/cli.py` | utility | request-response | `src/sva/cli.py` | exact |
| `src/sva/points/detector.py` | service | transform | `src/sva/perceive/runner.py` | partial |
| `src/sva/points/dao.py` | service | CRUD | `src/sva/events_dao.py` | exact |
| `src/sva/pipeline.py` | service | request-response | `src/sva/pipeline.py` | exact |
| `src/sva/models.py` | model | transform | `src/sva/models.py` | exact |
| `src/sva/events_dao.py` | service | CRUD | `src/sva/events_dao.py` | exact |
| `migrations/versions/0002_phase2_ingest_points.py` | migration | CRUD | `migrations/versions/0001_phase1_foundation.py` | exact |
| `tests/test_phase2_ingest_surface.py` | test | request-response | `tests/test_cli_e2e.py` | role-match |
| `tests/test_point_detector.py` | test | transform | `tests/test_ingest_transcode.py` | partial |
| `tests/test_db_migration.py` | test | CRUD | `tests/test_db_migration.py` | exact |
| `tests/test_models.py` | test | transform | `tests/test_models.py` | exact |

## Pattern Assignments

### `pyproject.toml` (config, transform)

**Analog:** `pyproject.toml`

**Dependency block pattern** (`pyproject.toml:5-25`):
```toml
[project]
name = "sva"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "pydantic>=2.9",
  "sqlalchemy>=2.0",
  "alembic>=1.13",
  "typer>=0.12",
]
```

Use the existing flat dependency list style when adding `fastapi`, `uvicorn`, and `yt-dlp`.

### `src/sva/config.py` (config, transform)

**Analog:** `src/sva/config.py`

**Settings field pattern** (`src/sva/config.py:12-29`):
```python
class Settings(BaseSettings):
    gemini_api_key: SecretStr = Field(..., alias="GEMINI_API_KEY")
    anthropic_api_key: SecretStr = Field(..., alias="ANTHROPIC_API_KEY")
    database_url: str = Field(..., alias="DATABASE_URL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )
```

**Singleton load pattern** (`src/sva/config.py:32-39`):
```python
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

settings: Settings = get_settings()
```

Use this for any Phase 2 settings like allowlisted hostnames, working download directory, or API bind options.

### `src/sva/ingest/ingest.py` (service, file-I/O)

**Analog:** `src/sva/ingest/ingest.py`

**Imports + ORM/dataclass pattern** (`src/sva/ingest/ingest.py:13-22`, `41-51`):
```python
from sqlalchemy import Column, DateTime, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from sva.db import Base, session_scope
from sva.ingest.probe import VideoMetadata, probe_metadata
from sva.ingest.sampler import window_offsets
from sva.ingest.transcode import transcode_to_cfr

@dataclass(frozen=True)
class IngestResult:
    video_id: str
    game_id: str
    source_path: str
    transcoded_path: str
```

**Core ingest pipeline pattern** (`src/sva/ingest/ingest.py:62-111`):
```python
def ingest_clip(path: Path | str, game_id: str | None = None, *, target_fps: int = 1) -> IngestResult:
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(f"Source video not found: {src}")

    effective_game_id = game_id or _generate_game_id()
    video_id = _generate_video_id()
    src_meta = probe_metadata(src)

    TRANSCODED_DIR.mkdir(parents=True, exist_ok=True)
    transcoded_path = TRANSCODED_DIR / f"{video_id}.mp4"
    out_meta = transcode_to_cfr(src, transcoded_path, fps=target_fps)
    windows = window_offsets(out_meta.duration_s, fps=target_fps, window_size_s=2.0)

    with session_scope() as session:
        row = JobRow(...)
        session.add(row)
```

Keep Phase 2 URL ingest as a resolver in front of this normalization path, not a second ingest implementation.

### `src/sva/ingest/sources.py` (service, file-I/O)

**Analog:** `src/sva/ingest/ingest.py`

**Path validation + fail-loud pattern** (`src/sva/ingest/ingest.py:76-87`):
```python
src = Path(path)
if not src.exists():
    raise FileNotFoundError(f"Source video not found: {src}")

TRANSCODED_DIR.mkdir(parents=True, exist_ok=True)
transcoded_path = TRANSCODED_DIR / f"{video_id}.mp4"
```

**Transactional persistence pattern** (`src/sva/ingest/ingest.py:91-99`):
```python
with session_scope() as session:
    row = JobRow(
        game_id=effective_game_id,
        video_id=video_id,
        status="ingested",
        source_path=str(src.resolve()),
        duration_s=out_meta.duration_s,
    )
    session.add(row)
```

Use this file for `LocalFileSource` / `RemoteUrlSource`, allowlist validation, `rights_acks` persistence, and `yt-dlp` download handoff into `ingest_clip()`.

### `src/sva/api/app.py` (route, request-response)

**Analog:** `src/sva/cli.py` with no exact HTTP analog in repo

**Thin surface over shared service pattern** (`src/sva/cli.py:35-49`):
```python
@app.command()
def ingest(...):
    console.print(...)
    if dry_run:
        raise typer.Exit(0)

    result = run_pipeline(clip, game_id=game_id)
```

**Structured response assembly pattern** (`src/sva/cli.py:51-65`):
```python
table = Table(title="Pipeline Result")
table.add_row("game_id", result.game_id)
table.add_row("video_id", result.video_id)
table.add_row("source", result.ingest.source_path)
table.add_row("transcoded", result.ingest.transcoded_path)
```

Planner should mirror the same thin-dispatch idea in FastAPI: parse request, call shared ingest/point service, serialize the returned dataclass/model. There is no local `FastAPI` or `APIRouter` pattern yet.

### `src/sva/cli.py` (utility, request-response)

**Analog:** `src/sva/cli.py`

**Typer signature pattern** (`src/sva/cli.py:35-42`):
```python
def ingest(
    clip: Annotated[Path, typer.Argument(exists=True, readable=True)],
    game_id: Annotated[str | None, typer.Option("--game-id", help="Override the generated game id")] = None,
    model: Annotated[str, typer.Option("--model", help="VLM model id (Phase 1 uses stub regardless)")] = "gemini-2.5-flash",
    fps: Annotated[int, typer.Option("--fps", help="Sampling fps; Phase 1 uses 1")] = 1,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print plan without executing")] = False,
) -> None:
```

**Output pattern** (`src/sva/cli.py:49-79`):
```python
result = run_pipeline(clip, game_id=game_id)
...
console.print(table)

with get_engine().connect() as conn:
    row = conn.execute(text("SELECT cost_usd FROM jobs WHERE game_id = :g"), {"g": game_id}).scalar()
```

Extend this same command instead of creating a second CLI entrypoint. Phase 2 flags belong here: URL input, `--ack-rights`, and caller identity.

### `src/sva/points/detector.py` (service, transform)

**Analog:** `src/sva/perceive/runner.py` and `src/sva/memory/retriever.py`

**Runner module pattern** (`src/sva/perceive/runner.py:11-26`):
```python
def make_default_perceiver() -> Perceiver:
    return GeminiPerceiver()

def run_window(ctx: TraceContext, window: PerceiveWindow, perceiver: Perceiver | None = None) -> Observation:
    p = perceiver or make_default_perceiver()
    return p.perceive(ctx, window)
```

**Small Pydantic query/input model pattern** (`src/sva/memory/retriever.py:14-35`):
```python
class RetrievalQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_candidate_type: str
    context_text: str = ""
    budget: int = Field(ge=1, le=20, default=6)
```

Use this package style for detector inputs/outputs: small explicit models for candidate spans/evidence, plus a runner function that hides the default implementation choice.

### `src/sva/points/dao.py` (service, CRUD)

**Analog:** `src/sva/events_dao.py`

**ORM mapping pattern** (`src/sva/events_dao.py:13-30`):
```python
class EventRow(Base):
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    event_id = Column(Text, nullable=False, unique=True)
    game_id = Column(Text, ForeignKey("jobs.game_id", ondelete="CASCADE"), nullable=False, index=True)
    point_id = Column(Text, nullable=True, index=True)
```

**DAO insert pattern** (`src/sva/events_dao.py:33-49`):
```python
def insert_event(event: Event) -> None:
    with session_scope() as session:
        row = EventRow(...)
        session.add(row)
```

Use the same small-DAO approach for `PointRow` and any `RightsAckRow`, not raw SQL scattered through pipeline code.

### `src/sva/pipeline.py` (service, request-response)

**Analog:** `src/sva/pipeline.py`

**Stage assembly point** (`src/sva/pipeline.py:50-57`):
```python
def run_pipeline(source_path: Path | str, game_id: str | None = None) -> PipelineResult:
    ing = ingest_clip(source_path, game_id=game_id)
    logger.info("Ingested %s -> %s (game_id=%s)", ing.source_path, ing.transcoded_path, ing.game_id)
```

**Per-window loop and insertion point** (`src/sva/pipeline.py:70-110`):
```python
observations: list[Observation] = []
for start_ms, end_ms in ing.windows:
    window = PerceiveWindow(...)
    try:
        obs = run_window(window_ctx, window, perceiver=perceiver)
        observations.append(obs)
    except Exception as exc:
        logger.exception("perceive failed for window %s: %s", window.window_id, exc)

if observations:
    interpret_ctx = TraceContext(..., point_id=None)
    event: Event = run_point(...)
    insert_event(event)
```

**Job completion update** (`src/sva/pipeline.py:112-129`):
```python
total_cost = _read_total_cost(ing.game_id)
with get_engine().begin() as conn:
    conn.execute(
        text("UPDATE jobs SET status = 'complete', updated_at = now() WHERE game_id = :g"),
        {"g": ing.game_id},
    )
```

Phase 2 should insert point detection immediately after ingest and before any window perception. Keep the orchestration thin; do not hide DAO writes inside unrelated helpers.

### `src/sva/models.py` (model, transform)

**Analog:** `src/sva/models.py`

**Versioned model pattern** (`src/sva/models.py:15-17`, `80-99`):
```python
from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION: Literal["1.0"] = "1.0"

class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    ...
```

**Event contract pattern** (`src/sva/models.py:102-122`):
```python
class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    event_id: str
    game_id: str
    point_id: str | None = None
    point_ordinal: int | None = None
    video_ts_ms: int = Field(ge=0)
    ...
```

Add Phase 2 point fields here rather than burying them in `details`. Preserve strict `extra="forbid"` and schema-versioned top-level models.

### `src/sva/events_dao.py` (service, CRUD)

**Analog:** `src/sva/events_dao.py`

**Column mapping pattern** (`src/sva/events_dao.py:18-30`):
```python
id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
event_id = Column(Text, nullable=False, unique=True)
game_id = Column(Text, ForeignKey("jobs.game_id", ondelete="CASCADE"), nullable=False, index=True)
point_id = Column(Text, nullable=True, index=True)
video_ts_ms = Column(Numeric(20, 0), nullable=False)
details = Column(JSONB, nullable=False, server_default="{}")
```

**Row construction pattern** (`src/sva/events_dao.py:33-49`):
```python
row = EventRow(
    event_id=event.event_id,
    game_id=event.game_id,
    point_id=event.point_id,
    video_ts_ms=event.video_ts_ms,
    type=event.type,
    team=event.team,
)
```

When Phase 2 makes `point_id` non-null and adds in-point timestamp storage, update this DAO in lockstep with the model and migration.

### `migrations/versions/0002_phase2_ingest_points.py` (migration, CRUD)

**Analog:** `migrations/versions/0001_phase1_foundation.py`

**Migration header pattern** (`migrations/versions/0001_phase1_foundation.py:1-18`):
```python
"""phase1 foundation: jobs + events tables, pgvector extension

Revision ID: 0001_phase1_foundation
Revises:
Create Date: 2026-04-21
"""
revision: str = "0001_phase1_foundation"
down_revision: str | None = None
```

**`create_table` pattern** (`migrations/versions/0001_phase1_foundation.py:21-112`):
```python
op.create_table(
    "events",
    sa.Column("event_id", sa.Text(), nullable=False, unique=True),
    sa.Column(
        "game_id",
        sa.Text(),
        sa.ForeignKey("jobs.game_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    sa.Column("point_id", sa.Text(), nullable=True, index=True),
    sa.Column("video_ts_ms", sa.BigInteger(), nullable=False),
)
```

Follow the same style for new `points` and `rights_acks` tables plus any `events` column tightening.

### `tests/test_phase2_ingest_surface.py` (test, request-response)

**Analog:** `tests/test_cli_e2e.py`

**Fixture/bootstrap pattern** (`tests/test_cli_e2e.py:27-44`):
```python
@pytest.fixture(scope="module", autouse=True)
def _ensure_vfr_fixture():
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not found")
    ...
```

**DB cleanup + end-to-end assertion pattern** (`tests/test_cli_e2e.py:47-84`):
```python
with get_engine().begin() as conn:
    conn.execute(text("DELETE FROM events WHERE game_id = :g"), {"g": game_id})
    conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})

result = run_pipeline(VFR_SYNTHETIC, game_id=game_id)

with get_engine().connect() as conn:
    job_row = conn.execute(text("SELECT status, cost_usd, duration_s FROM jobs WHERE game_id = :g"), {"g": game_id}).fetchone()
```

Use the same integration-test shape for CLI/API parity, URL allowlist rejection, and rights-ack logging.

### `tests/test_point_detector.py` (test, transform)

**Analog:** `tests/test_ingest_transcode.py`

**Direct module test pattern** (`tests/test_ingest_transcode.py:35-57`):
```python
def test_transcode_produces_cfr(tmp_path):
    from sva.ingest.transcode import transcode_to_cfr
    from sva.ingest.probe import probe_metadata

    dst = tmp_path / "out.mp4"
    out_meta = transcode_to_cfr(VFR_SYNTHETIC, dst, fps=1)
    assert dst.exists()
```

Use this same style for deterministic detector unit tests: feed a short fixture or synthetic evidence set directly into the detector, then assert exact point boundaries and confidence/evidence payloads.

### `tests/test_db_migration.py` (test, CRUD)

**Analog:** `tests/test_db_migration.py`

**Reachability + upgrade fixture pattern** (`tests/test_db_migration.py:15-35`):
```python
def _db_reachable() -> bool:
    ...

@pytest.fixture(scope="module")
def migrated_db():
    if not _db_reachable():
        pytest.skip("Postgres not reachable; start with `docker compose up -d db`")
    subprocess.run(["alembic", "upgrade", "head"], check=True, env=env)
    yield
```

**Schema assertion pattern** (`tests/test_db_migration.py:38-73`):
```python
rows = conn.execute(
    text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' ORDER BY table_name"
    )
).scalars().all()
assert "jobs" in rows
assert "events" in rows
```

Extend this file rather than creating a second migration smoke test.

### `tests/test_models.py` (test, transform)

**Analog:** `tests/test_models.py`

**Round-trip contract test pattern** (`tests/test_models.py:21-35`):
```python
obs = Observation(...)
payload = obs.model_dump_json()
rehydrated = Observation.model_validate_json(payload)
assert rehydrated == obs
assert rehydrated.schema_version == "1.0"
```

**Schema-guard pattern** (`tests/test_models.py:38-68`):
```python
with pytest.raises(ValidationError):
    Event(...)
```

Use the same tests when adding point-boundary evidence models and new non-null event point fields.

## Shared Patterns

### Thin Invocation Surfaces
**Sources:** `src/sva/cli.py:35-65`, `src/sva/pipeline.py:50-57`
**Apply to:** CLI and new API files
```python
result = run_pipeline(clip, game_id=game_id)
...
table.add_row("game_id", result.game_id)
```

Surface layers stay thin and delegate to shared service code. Phase 2 should keep CLI and HTTP as wrappers over the same ingest/point service.

### Transaction Boundaries
**Sources:** `src/sva/db.py:30-42`, `src/sva/events_dao.py:33-49`, `src/sva/ingest/ingest.py:91-99`
**Apply to:** New DAO/service persistence code
```python
@contextmanager
def session_scope() -> Iterator[Session]:
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise

with session_scope() as session:
    session.add(row)
```

Persist `points` and `rights_acks` through small DAO helpers using `session_scope()`.

### Versioned Pydantic Contracts
**Sources:** `src/sva/models.py:80-122`, `tests/test_models.py:21-68`
**Apply to:** New point models and `Event` updates
```python
class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    point_id: str | None = None
```

New point-boundary evidence payloads should be explicit models or tightly defined dicts, not loose untyped blobs.

### Package Export Style
**Source:** `src/sva/ingest/__init__.py:1-16`
**Apply to:** New `src/sva/points/__init__.py`
```python
from sva.ingest.ingest import IngestResult, JobRow, ingest_clip

__all__ = [
    "IngestResult",
    "JobRow",
    "ingest_clip",
]
```

If a new `points` package is added, expose a small stable public surface through `__all__`.

### Migration Style
**Sources:** `migrations/versions/0001_phase1_foundation.py:21-118`, `tests/test_db_migration.py:27-73`
**Apply to:** Phase 2 schema work
```python
op.create_table(...)
...
subprocess.run(["alembic", "upgrade", "head"], check=True, env=env)
```

Keep the migration self-contained and validate it through the existing smoke-test pattern.

### Error Handling Posture
**Sources:** `src/sva/ingest/ingest.py:76-78`, `src/sva/pipeline.py:86-90`, `src/sva/config.py:38-39`
**Apply to:** URL ingest and point detection
```python
if not src.exists():
    raise FileNotFoundError(...)

except Exception as exc:
    logger.exception(...)

settings: Settings = get_settings()
```

The repo currently prefers fail-loud service code with narrow catches at orchestration boundaries. Follow that posture for invalid URLs, missing rights ack, and anonymous-download failures.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `src/sva/api/app.py` | route | request-response | No existing `FastAPI`, `APIRouter`, or HTTP exception pattern exists in `src/` or `tests/`; planner should combine the thin-surface pattern from `src/sva/cli.py` with the synchronous API boundary from `02-RESEARCH.md`. |

## Metadata

**Analog search scope:** `src/sva`, `tests`, `migrations/versions`, phase context docs
**Files scanned:** 87
**Pattern extraction date:** 2026-04-23
