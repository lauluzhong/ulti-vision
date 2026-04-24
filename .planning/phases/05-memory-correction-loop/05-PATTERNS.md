# Phase 05: Memory & Correction Loop - Pattern Map

**Mapped:** 2026-04-24
**Files analyzed:** 14 likely Phase 5 files
**Analogs found:** 13 / 14

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/sva/models.py` | model | transform | `src/sva/models.py` | self |
| `src/sva/memory/retriever.py` | service | query | `src/sva/perceive/runner.py` | role-match |
| `src/sva/memory/records_dao.py` | service | CRUD | `src/sva/observations_dao.py` | exact |
| `src/sva/memory/corrections_dao.py` | service | CRUD | `src/sva/events_dao.py` | exact |
| `src/sva/memory/writer.py` | service | transform | `src/sva/interpret/rules.py` | role-match |
| `src/sva/memory/__init__.py` | package | export | `src/sva/interpret/__init__.py` | exact |
| `migrations/versions/0007_phase5_memory_and_corrections.py` | migration | CRUD | `migrations/versions/0005_phase3_observations.py` | exact |
| `tests/test_memory_retriever.py` | test | query | `tests/test_perceive_runner.py` | role-match |
| `tests/test_memory_records_dao.py` | test | CRUD | `tests/test_observations_dao.py` | exact |
| `tests/test_corrections_dao.py` | test | CRUD | `tests/test_events_dao.py` | exact |
| `tests/test_memory_writer.py` | test | transform | `tests/test_interpret_rules.py` | role-match |
| `tests/test_db_migration.py` | test | migration | `tests/test_db_migration.py` | self |
| `src/sva/interpret/prompt.py` | service | transform | `src/sva/interpret/prompt.py` | self |
| `src/sva/interpret/adapters/claude.py` | service | request-response | `src/sva/interpret/adapters/claude.py` | self |

## Pattern Assignments

### `src/sva/memory/records_dao.py` (service, CRUD)

**Analog:** `src/sva/observations_dao.py`

**ORM row + bulk insert pattern** ([src/sva/observations_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/observations_dao.py:13)):
```python
class ObservationRow(Base):
    __tablename__ = "observations"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    observation_id = Column(Text, nullable=False, unique=True)
```

**Batch persistence helper** ([src/sva/observations_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/observations_dao.py:37)):
```python
def insert_observations(..., observations: list[Observation], ...) -> None:
    with session_scope() as session:
        session.add_all([...])
```

**Phase 5 guidance**
- Follow the same narrow DAO shape: one ORM row class, one insert helper, one or two query helpers.
- Persist canonical `MemoryRecord` payloads or normalized fields directly, not provider-shaped embedding payloads.

---

### `src/sva/memory/corrections_dao.py` (service, CRUD)

**Analog:** `src/sva/events_dao.py`

**Canonical row builder pattern** ([src/sva/events_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/events_dao.py:37)):
```python
def _event_row_from_event(event: Event) -> EventRow:
    return EventRow(...)
```

**Filtered list helper pattern** ([src/sva/events_dao.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/events_dao.py:72)):
```python
def list_event_rows(game_id: str, *, point_id: str | None = None, event_type: str | None = None, team: str | None = None) -> list[EventRow]:
```

**Phase 5 guidance**
- Build a canonical correction-row constructor from a correction model or dict.
- Provide targeted list helpers by `coach_id`, `source_event_id`, and maybe `game_id` rather than one giant service layer.

---

### `migrations/versions/0007_phase5_memory_and_corrections.py` (migration, CRUD)

**Analog:** `migrations/versions/0005_phase3_observations.py`

**Create-table + index pattern** ([migrations/versions/0005_phase3_observations.py](/Users/lauluzhong/Documents/Sports Video Analytics/migrations/versions/0005_phase3_observations.py:19)):
```python
op.create_table(
    "observations",
    sa.Column(...),
)
op.create_index("ix_observations_game_id", "observations", ["game_id"], unique=False)
```

**Phase 5 guidance**
- Keep one migration for the initial memory/corrections substrate.
- Use JSONB for flexible provenance snapshots and tags if needed.
- Add only the indexes Phase 5 queries will actually use.

---

### `src/sva/memory/retriever.py` (service, query)

**Primary analog:** current `src/sva/memory/retriever.py`

**Fixed signature to preserve** ([src/sva/memory/retriever.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/memory/retriever.py:23)):
```python
async def retrieve(
    self,
    query: RetrievalQuery,
    tags: list[str] | None = None,
    limit: int | None = None,
) -> list[MemoryRecord]:
```

**Supportive orchestrator analog:** `src/sva/perceive/runner.py`

**Phase 5 guidance**
- Keep the public retriever class small and async even if its internals call synchronous DAO helpers.
- Treat scope resolution, tag filtering, and ranking as explicit steps instead of one opaque query blob.
- Prefer deterministic fallback ordering over fabricated semantic confidence when embeddings are unavailable.

---

### `src/sva/memory/writer.py` (service, transform)

**Analog:** `src/sva/interpret/rules.py`

**Thin deterministic helper style** ([src/sva/interpret/rules.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/interpret/rules.py:1)):
- load canonical data
- return structured validation results
- keep decision logic small and testable

**Phase 5 guidance**
- Promotion checks should live in explicit functions like `can_promote_global(...)` or `build_correction_memory_records(...)`.
- Keep side effects separated from decision logic so tests can prove contamination controls without requiring a live DB.

---

### `tests/test_memory_retriever.py` (test, query)

**Current analog:** `tests/test_memory_retriever.py`

**Signature-lock pattern** ([tests/test_memory_retriever.py](/Users/lauluzhong/Documents/Sports Video Analytics/tests/test_memory_retriever.py:15)):
```python
sig = inspect.signature(MemoryRetriever.retrieve)
params = list(sig.parameters.keys())
assert params == ["self", "query", "tags", "limit"]
```

**Phase 5 guidance**
- Preserve the existing signature-lock test.
- Add behavioral tests for scope filtering, tag-first narrowing, and bounded result count.

---

### `src/sva/interpret/prompt.py` and `src/sva/interpret/adapters/claude.py` (integration points)

**Analogs:** current self files

**Explicit prompt section pattern** ([src/sva/interpret/prompt.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/interpret/prompt.py:22)):
```python
"Retrieved memory records:\n"
f"{memory_block}\n\n"
```

**Normalization seam** ([src/sva/interpret/adapters/claude.py](/Users/lauluzhong/Documents/Sports Video Analytics/src/sva/interpret/adapters/claude.py:52)):
```python
"memory_refs": event.memory_refs,
```

**Phase 5 guidance**
- Keep memory as an explicit prompt section.
- If the model omits `memory_refs`, normalize from the retrieved memory ids rather than losing the audit trail.

## Recommendations

- Use the Phase 3/4 DAO+migration cadence directly for Phase 5 instead of inventing a bigger repository pattern.
- Keep correction and promotion logic isolated from HTTP/API concerns.
- Treat vector ranking as a later refinement inside the retriever seam, not as a prerequisite for landing the persistence substrate.

---
*Phase: 05-memory-correction-loop*
*Pattern map generated: 2026-04-24*
