"""Memory retriever stub contract tests (CONTEXT D-08)."""

from __future__ import annotations

import asyncio

from sva.memory import MemoryRetriever, RetrievalQuery


def test_retriever_returns_empty_list():
    r = MemoryRetriever()
    q = RetrievalQuery(event_candidate_type="turnover", context_text="drop near sideline")
    result = asyncio.run(r.retrieve(q))
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
