"""Memory retriever behavior and contract tests."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sva.memory import MemoryRetriever, RetrievalQuery
from sva.models import MemoryRecord, MemorySource


def _record(memory_id: str, *, scope: str, kind: str = "rule", tags: list[str]) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        kind=kind,
        tags=tags,
        scope=scope,
        source=MemorySource(origin="seed" if kind == "rule" else "correction"),
        created_at=datetime.now(timezone.utc),
    )


def test_retriever_returns_scope_and_tag_filtered_records(monkeypatch):
    calls: list[tuple[tuple[str, ...], str | None, int | None]] = []

    def fake_list_memory_records(*, scopes=None, kinds=None, tag=None, limit=None):
        _ = kinds
        calls.append((tuple(scopes or []), tag, limit))
        fixtures = {
            (("coach:coach_1",), "turnover"): [
                _record("mem_coach_turnover", scope="coach:coach_1", kind="correction", tags=["turnover"])
            ],
            (("coach:coach_1",), "sideline"): [
                _record("mem_coach_sideline", scope="coach:coach_1", kind="correction", tags=["sideline"])
            ],
            (("global",), "turnover"): [
                _record("mem_global_turnover", scope="global", tags=["turnover"])
            ],
            (("global",), "sideline"): [],
        }
        return fixtures.get((tuple(scopes or []), tag), [])

    monkeypatch.setattr("sva.memory.retriever.list_memory_records", fake_list_memory_records)

    r = MemoryRetriever()
    q = RetrievalQuery(
        event_candidate_type="turnover",
        context_text="drop near sideline",
        current_coach_id="coach_1",
        budget=3,
    )
    result = asyncio.run(r.retrieve(q, tags=["sideline"]))

    assert [record.memory_id for record in result] == [
        "mem_coach_turnover",
        "mem_coach_sideline",
        "mem_global_turnover",
    ]
    assert calls == [
        (("coach:coach_1",), "turnover", 3),
        (("coach:coach_1",), "sideline", 3),
        (("global",), "turnover", 3),
    ]


def test_retriever_respects_limit_and_returns_empty_when_no_tag_match(monkeypatch):
    def fake_list_memory_records(*, scopes=None, kinds=None, tag=None, limit=None):
        _ = scopes, kinds, limit
        if tag == "goal":
            return []
        return [
            _record("mem_one", scope="global", tags=[tag or "completion"]),
            _record("mem_two", scope="global", tags=[tag or "completion"]),
        ]

    monkeypatch.setattr("sva.memory.retriever.list_memory_records", fake_list_memory_records)

    r = MemoryRetriever()
    goal_query = RetrievalQuery(event_candidate_type="goal", context_text="clean score")
    result = asyncio.run(r.retrieve(goal_query))
    assert result == []

    completion_query = RetrievalQuery(event_candidate_type="completion", context_text="swing pass", budget=6)
    limited = asyncio.run(r.retrieve(completion_query, limit=1))
    assert [record.memory_id for record in limited] == ["mem_one"]


def test_retriever_signature_matches_phase5_contract():
    """Phase 5 must not change the signature — only the body."""
    import inspect

    sig = inspect.signature(MemoryRetriever.retrieve)
    params = list(sig.parameters.keys())
    assert params == ["self", "query", "tags", "limit"], (
        f"Retriever.retrieve signature changed — Phase 5 must preserve this shape: {params}"
    )
    assert inspect.iscoroutinefunction(MemoryRetriever.retrieve), "retrieve must be async"
