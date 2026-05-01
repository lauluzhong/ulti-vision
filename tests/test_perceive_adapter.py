"""Phase 1 tests: GeminiPerceiver stub emits a valid Observation + Langfuse trace path."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import text

def _db_reachable() -> bool:
    try:
        from sva.db import get_engine

        with get_engine().connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

@pytest.mark.skipif(not _db_reachable(), reason="Postgres unreachable")
def test_gemini_perceiver_emits_valid_observation_with_db_cost(monkeypatch):
    """Verify the GeminiPerceiver records cost into the jobs row with the
    real Pydantic validation path. The Gemini API call itself is mocked —
    this test does NOT require a real video or API key."""
    from google.genai import types
    from sva.db import get_engine
    from sva.observability import TraceContext
    from sva.perceive import GeminiPerceiver, PerceiveWindow

    game_id = "test_perceive_game_1"
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})
        conn.execute(
            text("INSERT INTO jobs (game_id, video_id, status) VALUES (:g, :v, 'streaming')"),
            {"g": game_id, "v": "vid_test"},
        )

    fake_observation_json = (
        '{"schema_version":"2.0","observation_id":"obs_smoke_1","window_id":"win_1",'
        '"video_id":"vid_test","video_ts_start_ms":0,"video_ts_end_ms":2000,'
        '"observation_ts_ms":1000,"scene":{},"disc":{},"players":{},'
        '"text_observed":[],'
        '"model":{"provider":"gemini","model_id":"ignored","version":"ignored"},'
        '"confidence_overall":0.5}'
    )

    class FakeFiles:
        def upload(self, *, file, config):
            return SimpleNamespace(name="files/uploaded-1", uri="gs://fake/video.mp4", state="ACTIVE", mime_type="video/mp4")

        def get(self, *, name):
            return SimpleNamespace(name=name, uri="gs://fake/video.mp4", state="ACTIVE", mime_type="video/mp4")

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            return SimpleNamespace(
                model_version="gemini-2.5-flash-001",
                response_id="resp_1",
                text=fake_observation_json,
                parsed=None,
                usage_metadata=types.GenerateContentResponseUsageMetadata(
                    prompt_token_count=200,
                    candidates_token_count=40,
                    total_token_count=240,
                ),
            )

    fake_client = SimpleNamespace(files=FakeFiles(), models=FakeModels())
    monkeypatch.setattr("sva.perceive.adapters.gemini._get_client", lambda: fake_client)
    monkeypatch.setattr("sva.observability.langfuse.get_langfuse", lambda: None)

    window = PerceiveWindow(
        window_id="win_1",
        video_id="vid_test",
        video_ts_start_ms=0,
        video_ts_end_ms=2000,
        transcoded_path="/tmp/fake.mp4",
    )
    ctx = TraceContext(stage="perceive", model="gemini-2.5-flash", video_id="vid_test", game_id=game_id)

    obs = GeminiPerceiver().perceive(ctx, window)
    assert obs.schema_version == "2.0"
    assert obs.model.provider == "gemini"
    assert obs.model.model_id == "gemini-2.5-flash"
    assert obs.window_id == "win_1"
    assert 0 <= obs.confidence_overall <= 1

    # OBS-01: cost should have been recorded on the jobs row.
    with get_engine().connect() as conn:
        cost = conn.execute(
            text("SELECT cost_usd FROM jobs WHERE game_id = :g"),
            {"g": game_id},
        ).scalar()
    assert cost is not None
    assert float(cost) > 0

    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})

def test_gemini_perceiver_populates_prompt_hash_and_ambiguity_fields(monkeypatch):
    from google.genai import types
    from sva.observability import TraceContext
    from sva.perceive import GeminiPerceiver, PerceiveWindow

    class FakeFiles:
        def upload(self, *, file, config):
            return SimpleNamespace(
                name="files/uploaded-1",
                uri="gs://fake/video.mp4",
                state="ACTIVE",
                mime_type="video/mp4",
            )

        def get(self, *, name):
            return SimpleNamespace(name=name, uri="gs://fake/video.mp4", state="ACTIVE", mime_type="video/mp4")

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            assert model == "gemini-2.5-flash"
            # New API: video_metadata time slice on a Content/Part with FileData,
            # not response_schema (we removed it due to a google-genai 1.73 SDK bug).
            return SimpleNamespace(
                model_version="gemini-2.5-flash-001",
                response_id="resp_123",
                text=None,  # parsed path takes precedence in the adapter
                usage_metadata=types.GenerateContentResponseUsageMetadata(
                    prompt_token_count=321,
                    candidates_token_count=45,
                    total_token_count=366,
                ),
                parsed={
                    "schema_version": "2.0",
                    "observation_id": "obs_fake_001",
                    "window_id": "ignored_by_adapter",
                    "video_id": "ignored_by_adapter",
                    "video_ts_start_ms": 0,
                    "video_ts_end_ms": 0,
                    "observation_ts_ms": 900,
                    "scene": {
                        "field_visible": "partial",
                        "camera": "sideline",
                        "lighting": "ok",
                        "obstruction": False,
                        "multiple_discs_possible": True,
                    },
                    "disc": {
                        "visible": False,
                        "visibility_quality": "likely_present_not_visible",
                        "in_air": False,
                        },
                    "players": {"dark_count_visible": 5, "light_count_visible": 4},
                    "text_observed": [],
                    "model": {
                        "provider": "gemini",
                        "model_id": "ignored",
                        "version": "ignored",
                    },
                    "confidence_overall": 0.4,
                },
            )

    fake_client = SimpleNamespace(files=FakeFiles(), models=FakeModels())
    monkeypatch.setattr("sva.perceive.adapters.gemini._get_client", lambda: fake_client)
    monkeypatch.setattr("sva.observability.langfuse.get_langfuse", lambda: None)
    monkeypatch.setattr("sva.observability.cost.record_job_cost", lambda game_id, delta_usd: None)

    window = PerceiveWindow(
        window_id="win_ambiguous_1",
        video_id="vid_test",
        video_ts_start_ms=0,
        video_ts_end_ms=2000,
        transcoded_path="/tmp/fake.mp4",
    )
    ctx = TraceContext(stage="perceive", model="gemini-2.5-flash", video_id="vid_test", game_id="game_test")

    obs = GeminiPerceiver().perceive(ctx, window)
    assert obs.window_id == "win_ambiguous_1"
    assert obs.video_id == "vid_test"
    assert obs.model.provider == "gemini"
    assert obs.model.model_id == "gemini-2.5-flash"
    assert obs.scene.multiple_discs_possible is True
    assert obs.disc.visibility_quality == "likely_present_not_visible"
    assert obs.raw_response_ref == "resp_123"

def test_gemini_perceiver_retries_once_then_succeeds(monkeypatch):
    from google.genai import types
    from sva.observability import TraceContext
    from sva.perceive import GeminiPerceiver, PerceiveWindow

    class RetryableError(RuntimeError):
        status_code = 429

    calls = {"count": 0}

    class FakeFiles:
        def upload(self, *, file, config):
            return SimpleNamespace(
                name="files/uploaded-2", uri="gs://fake/video.mp4", state="ACTIVE", mime_type="video/mp4"
            )

        def get(self, *, name):
            return SimpleNamespace(name=name, uri="gs://fake/video.mp4", state="ACTIVE", mime_type="video/mp4")

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RetryableError("rate limit")
            return SimpleNamespace(
                model_version="gemini-2.5-flash-001",
                response_id="resp_456",
                usage_metadata=types.GenerateContentResponseUsageMetadata(
                    prompt_token_count=100,
                    candidates_token_count=10,
                    total_token_count=110,
                ),
                parsed={
                    "schema_version": "2.0",
                    "observation_id": "obs_retry_001",
                    "window_id": "win_retry_1",
                    "video_id": "vid_retry",
                    "video_ts_start_ms": 0,
                    "video_ts_end_ms": 2000,
                    "observation_ts_ms": 1000,
                    "scene": {},
                    "disc": {},
                    "players": {},
                    "text_observed": [],
                    "model": {"provider": "gemini", "model_id": "ignored", "version": "ignored"},
                    "confidence_overall": 0.5,
                },
            )

    fake_client = SimpleNamespace(files=FakeFiles(), models=FakeModels())
    monkeypatch.setattr("sva.perceive.adapters.gemini._get_client", lambda: fake_client)
    monkeypatch.setattr("sva.perceive.adapters.gemini.time.sleep", lambda _: None)
    monkeypatch.setattr("sva.observability.langfuse.get_langfuse", lambda: None)
    monkeypatch.setattr("sva.observability.cost.record_job_cost", lambda game_id, delta_usd: None)

    window = PerceiveWindow(
        window_id="win_retry_1",
        video_id="vid_retry",
        video_ts_start_ms=0,
        video_ts_end_ms=2000,
        transcoded_path="/tmp/fake.mp4",
    )
    ctx = TraceContext(stage="perceive", model="gemini-2.5-flash", video_id="vid_retry", game_id="game_retry")

    obs = GeminiPerceiver().perceive(ctx, window)
    # observation_id is force-overridden by the adapter (the LLM has no business
    # inventing system IDs), so we just verify it's a fresh non-empty string.
    assert obs.observation_id and obs.observation_id.startswith("obs_")
    assert calls["count"] == 2

def test_gemini_perceiver_raises_after_retry_exhaustion(monkeypatch):
    from google.genai import types
    from sva.observability import TraceContext
    from sva.perceive import GeminiPerceiver, PerceiveWindow

    class RetryableError(RuntimeError):
        status_code = 429

    class FakeFiles:
        def upload(self, *, file, config):
            return SimpleNamespace(
                name="files/uploaded-3", uri="gs://fake/video.mp4", state="ACTIVE", mime_type="video/mp4"
            )

        def get(self, *, name):
            return SimpleNamespace(name=name, uri="gs://fake/video.mp4", state="ACTIVE", mime_type="video/mp4")

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            raise RetryableError("too many requests")

    fake_client = SimpleNamespace(files=FakeFiles(), models=FakeModels())
    monkeypatch.setattr("sva.perceive.adapters.gemini._get_client", lambda: fake_client)
    monkeypatch.setattr("sva.perceive.adapters.gemini.time.sleep", lambda _: None)
    monkeypatch.setattr("sva.observability.langfuse.get_langfuse", lambda: None)
    monkeypatch.setattr("sva.observability.cost.record_job_cost", lambda game_id, delta_usd: None)

    window = PerceiveWindow(
        window_id="win_retry_2",
        video_id="vid_retry",
        video_ts_start_ms=0,
        video_ts_end_ms=2000,
        transcoded_path="/tmp/fake.mp4",
    )
    ctx = TraceContext(stage="perceive", model="gemini-2.5-flash", video_id="vid_retry", game_id="game_retry")

    with pytest.raises(RetryableError):
        GeminiPerceiver().perceive(ctx, window)
