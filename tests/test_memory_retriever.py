"""Memory retriever behavior and contract tests."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sva.memory import MemoryRetriever, RetrievalQuery
from sva.memory.embeddings import content_hash
from sva.models import MemoryRecord, MemorySource


def _record(
    memory_id: str,
    *,
    scope: str,
    kind: str = "rule",
    tags: list[str],
    embedding_input: str = "",
) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        kind=kind,
        tags=tags,
        scope=scope,
        source=MemorySource(origin="seed" if kind == "rule" else "correction"),
        embedding_input=embedding_input,
        created_at=datetime.now(timezone.utc),
    )


class _FakeProvider:
    provider_name = "fake"
    model_id = "fake-embeddings-v1"
    output_dimensionality = 2

    def __init__(self) -> None:
        self.query_inputs: list[str] = []
        self.document_inputs: list[list[str]] = []

    def embed_query(self, text: str) -> list[float]:
        self.query_inputs.append(text)
        return [1.0, 0.0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_inputs.append(list(texts))
        vectors: list[list[float]] = []
        for text in texts:
            lowered = text.lower()
            if "drop near sideline" in lowered:
                vectors.append([1.0, 0.0])
            elif "stall-count bailout" in lowered:
                vectors.append([0.2, 0.98])
            else:
                vectors.append([0.0, 1.0])
        return vectors


class _ExplodingProvider(_FakeProvider):
    def embed_query(self, text: str) -> list[float]:
        raise RuntimeError("embedding service unavailable")


def test_retriever_semantically_ranks_candidates_and_persists_missing_embeddings(monkeypatch):
    calls: list[tuple[tuple[str, ...], str | None, int | None]] = []
    upserts: list[tuple[str, str, str, str, list[float]]] = []

    coach_turnover = _record(
        "mem_coach_turnover",
        scope="coach:coach_1",
        kind="correction",
        tags=["turnover"],
        embedding_input="stall-count bailout throwaway from reset space",
    )
    global_drop = _record(
        "mem_global_drop",
        scope="global",
        tags=["turnover", "sideline"],
        embedding_input="receiver drop near sideline on under cut",
    )
    global_block = _record(
        "mem_global_block",
        scope="global",
        tags=["turnover"],
        embedding_input="layout block in the lane after floaty pass",
    )

    def fake_list_memory_records(*, scopes=None, kinds=None, tag=None, limit=None):
        _ = kinds
        calls.append((tuple(scopes or []), tag, limit))
        fixtures = {
            (("coach:coach_1",), "turnover"): [coach_turnover],
            (("coach:coach_1",), "sideline"): [],
            (("global",), "turnover"): [global_drop, global_block],
            (("global",), "sideline"): [global_drop],
        }
        return fixtures.get((tuple(scopes or []), tag), [])

    def fake_list_memory_embeddings(*, memory_ids, provider=None, model_id=None):
        assert provider == "fake"
        assert model_id == "fake-embeddings-v1"
        assert memory_ids == ["mem_coach_turnover", "mem_global_drop", "mem_global_block"]
        return {
            "mem_global_block": {
                "content_hash": content_hash(global_block.embedding_input),
                "vector": [0.0, 1.0],
            }
        }

    def fake_upsert_memory_embedding(*, memory_id, provider, model_id, content_hash, vector):
        upserts.append((memory_id, provider, model_id, content_hash, vector))

    monkeypatch.setattr("sva.memory.retriever.list_memory_records", fake_list_memory_records)
    monkeypatch.setattr("sva.memory.retriever.list_memory_embeddings", fake_list_memory_embeddings)
    monkeypatch.setattr("sva.memory.retriever.upsert_memory_embedding", fake_upsert_memory_embedding)

    provider = _FakeProvider()
    retriever = MemoryRetriever(embedding_provider=provider)
    query = RetrievalQuery(
        event_candidate_type="turnover",
        context_text="receiver drop near sideline after short under cut",
        current_coach_id="coach_1",
        budget=2,
    )
    result = asyncio.run(retriever.retrieve(query, tags=["sideline"]))

    assert [record.memory_id for record in result] == [
        "mem_global_drop",
        "mem_coach_turnover",
    ]
    assert calls == [
        (("coach:coach_1",), "turnover", 6),
        (("coach:coach_1",), "sideline", 6),
        (("global",), "turnover", 6),
        (("global",), "sideline", 6),
    ]
    assert provider.query_inputs == [
        "event_candidate_type: turnover\ncontext: receiver drop near sideline after short under cut\ncoach_scope: coach_1"
    ]
    assert provider.document_inputs == [[
        coach_turnover.embedding_input,
        global_drop.embedding_input,
    ]]
    assert upserts == [
        (
            "mem_coach_turnover",
            "fake",
            "fake-embeddings-v1",
            content_hash(coach_turnover.embedding_input),
            [0.2, 0.98],
        ),
        (
            "mem_global_drop",
            "fake",
            "fake-embeddings-v1",
            content_hash(global_drop.embedding_input),
            [1.0, 0.0],
        ),
    ]


def test_retriever_falls_back_to_deterministic_order_when_embeddings_fail(monkeypatch):
    def fake_list_memory_records(*, scopes=None, kinds=None, tag=None, limit=None):
        _ = scopes, kinds, limit
        if tag != "completion":
            return []
        return [
            _record("mem_one", scope="global", tags=["completion"], embedding_input="first"),
            _record("mem_two", scope="global", tags=["completion"], embedding_input="second"),
        ]

    monkeypatch.setattr("sva.memory.retriever.list_memory_records", fake_list_memory_records)
    monkeypatch.setattr(
        "sva.memory.retriever.list_memory_embeddings",
        lambda **kwargs: {},
    )
    monkeypatch.setattr(
        "sva.memory.retriever.upsert_memory_embedding",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not persist on fallback")),
    )

    retriever = MemoryRetriever(embedding_provider=_ExplodingProvider())
    query = RetrievalQuery(event_candidate_type="completion", context_text="swing pass", budget=2)
    result = asyncio.run(retriever.retrieve(query))

    assert [record.memory_id for record in result] == ["mem_one", "mem_two"]


def test_retriever_returns_empty_when_no_tag_match(monkeypatch):
    monkeypatch.setattr(
        "sva.memory.retriever.list_memory_records",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(
        "sva.memory.retriever.list_memory_embeddings",
        lambda **kwargs: {},
    )
    monkeypatch.setattr(
        "sva.memory.retriever.upsert_memory_embedding",
        lambda **kwargs: None,
    )

    retriever = MemoryRetriever(embedding_provider=_FakeProvider())
    query = RetrievalQuery(event_candidate_type="goal", context_text="clean score")
    result = asyncio.run(retriever.retrieve(query))

    assert result == []


def test_retriever_signature_matches_phase5_contract():
    """Phase 5 must not change the signature — only the body."""
    import inspect

    sig = inspect.signature(MemoryRetriever.retrieve)
    params = list(sig.parameters.keys())
    assert params == ["self", "query", "tags", "limit"], (
        f"Retriever.retrieve signature changed — Phase 5 must preserve this shape: {params}"
    )
    assert inspect.iscoroutinefunction(MemoryRetriever.retrieve), "retrieve must be async"
