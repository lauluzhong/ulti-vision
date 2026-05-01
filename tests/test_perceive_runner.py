"""Unit tests for cache-first run_window behavior."""

from __future__ import annotations

from sva.models import DiscObservation, ModelMetadata, Observation, PlayerCounts, SceneObservation
from sva.observability import TraceContext
from sva.perceive.adapters.base import PerceiveWindow
from sva.perceive.runner import run_window

def _observation(window: PerceiveWindow) -> Observation:
    return Observation(
        observation_id=f"obs_{window.window_id}",
        window_id=window.window_id,
        video_id=window.video_id,
        video_ts_start_ms=window.video_ts_start_ms,
        video_ts_end_ms=window.video_ts_end_ms,
        observation_ts_ms=(window.video_ts_start_ms + window.video_ts_end_ms) // 2,
        scene=SceneObservation(),
        disc=DiscObservation(),
        players=PlayerCounts(),
        text_observed=[],
        model=ModelMetadata(provider="dummy", model_id="dummy-vlm", version="test"),
        confidence_overall=0.5,
    )

def test_run_window_uses_cached_observation_without_calling_perceiver(monkeypatch):
    window = PerceiveWindow(
        window_id="win_vid_test_1fps_0_2000",
        video_id="vid_test",
        video_ts_start_ms=0,
        video_ts_end_ms=2000,
        transcoded_path="/tmp/fake.mp4",
    )
    cached = _observation(window)
    calls = {"perceive": 0}

    class DummyPerceiver:
        def prompt_hash_for(self, window):
            return "hash_cache"

        def perceive(self, ctx, window):
            calls["perceive"] += 1
            return _observation(window)

    monkeypatch.setattr(
        "sva.perceive.runner.list_cached_observations",
        lambda **kwargs: [cached],
    )
    monkeypatch.setattr("sva.perceive.runner.get_langfuse", lambda: None)

    ctx = TraceContext(stage="perceive", model="dummy-vlm", video_id="vid_test", game_id="game_test")
    result = run_window(ctx, window, perceiver=DummyPerceiver())

    assert result == cached
    assert calls["perceive"] == 0

def test_run_window_invokes_perceiver_and_persists_on_cache_miss(monkeypatch):
    window = PerceiveWindow(
        window_id="win_vid_test_1fps_0_2000",
        video_id="vid_test",
        video_ts_start_ms=0,
        video_ts_end_ms=2000,
        transcoded_path="/tmp/fake.mp4",
    )
    stored: list[tuple[str, Observation]] = []

    class DummyPerceiver:
        def prompt_hash_for(self, window):
            return "hash_miss"

        def perceive(self, ctx, window):
            assert ctx.prompt_version_hash == "hash_miss"
            return _observation(window)

    monkeypatch.setattr("sva.perceive.runner.list_cached_observations", lambda **kwargs: [])

    ctx = TraceContext(stage="perceive", model="dummy-vlm", video_id="vid_test", game_id="game_test")
    result = run_window(
        ctx,
        window,
        perceiver=DummyPerceiver(),
        on_cache_miss=lambda observation, prompt_hash: stored.append((prompt_hash, observation)),
    )

    assert result.window_id == window.window_id
    assert stored == [("hash_miss", result)]
