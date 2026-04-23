"""Unit tests for Phase 2 point-aware pipeline orchestration."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from sva.ingest.ingest import IngestResult
from sva.models import ModelMetadata, Observation
from sva.points.types import BoundarySignal, PointBoundaryCandidate, PointRecord


def test_run_pipeline_detects_points_before_perception_and_persists_point_scoped_events(monkeypatch):
    from sva.models import DiscObservation, Event, PlayerCounts, SceneObservation
    from sva.pipeline import run_pipeline

    order: list[str] = []
    inserted_events: list[Event] = []
    points = [
        PointRecord(
            point_id="game_test:pt_001",
            game_id="game_test",
            point_ordinal=1,
            start_video_ts_ms=0,
            end_video_ts_ms=1500,
            confidence=0.9,
            boundary_evidence=[BoundarySignal(source="pull", video_ts_ms=0, confidence=0.9)],
        ),
        PointRecord(
            point_id="game_test:pt_002",
            game_id="game_test",
            point_ordinal=2,
            start_video_ts_ms=1501,
            end_video_ts_ms=4000,
            confidence=0.9,
            boundary_evidence=[BoundarySignal(source="scoreboard", video_ts_ms=1600, confidence=0.9)],
        ),
    ]

    def fake_ingest_clip(source_path, game_id=None):
        order.append("ingest")
        return IngestResult(
            video_id="vid_test",
            game_id=game_id or "game_test",
            source_path=str(source_path),
            transcoded_path="/tmp/fake.mp4",
            duration_s=4.0,
            status="ingested",
            windows=[(0, 1000), (2000, 3000)],
            source_metadata=SimpleNamespace(duration_s=4.0),
            transcoded_metadata=SimpleNamespace(duration_s=4.0),
        )

    def fake_build_candidates(ing):
        return [
            PointBoundaryCandidate(
                start_video_ts_ms=0,
                end_video_ts_ms=4000,
                pull=BoundarySignal(source="pull", video_ts_ms=0, confidence=1.0),
            )
        ]

    def fake_detect_points(game_id, candidates):
        order.append("detect")
        assert candidates
        return points

    def fake_insert_points(detected_points):
        order.append("persist_points")
        assert detected_points == points

    def fake_list_points(game_id):
        return points

    class DummyRetriever:
        async def retrieve(self, query):
            order.append("retrieve")
            return []

    def fake_run_window(ctx, window, perceiver=None):
        order.append(f"perceive:{ctx.point_id}")
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
            model=ModelMetadata(provider="dummy", model_id="dummy-vlm", version="test"),
            confidence_overall=0.5,
        )

    def fake_run_point(ctx, observations, interpreter=None, retrieved=None):
        order.append(f"interpret:{ctx.point_id}")
        return Event(
            event_id=f"evt_{ctx.point_id}",
            game_id=ctx.game_id,
            point_id=ctx.point_id or "missing",
            point_ordinal=ctx.point_ordinal or 0,
            video_ts_ms=observations[0].observation_ts_ms,
            in_point_ts_ms=0,
            type="unknown",
            team="unknown",
            model=ModelMetadata(provider="dummy", model_id="dummy-llm", version="test"),
        )

    def fake_insert_event(event):
        order.append(f"persist_event:{event.point_id}")
        inserted_events.append(event)

    monkeypatch.setattr("sva.pipeline.ingest_clip", fake_ingest_clip)
    monkeypatch.setattr("sva.pipeline._build_point_boundary_candidates", fake_build_candidates)
    monkeypatch.setattr("sva.pipeline.detect_points", fake_detect_points)
    monkeypatch.setattr("sva.pipeline.insert_points", fake_insert_points)
    monkeypatch.setattr("sva.pipeline.list_points", fake_list_points)
    monkeypatch.setattr("sva.pipeline.MemoryRetriever", DummyRetriever)
    monkeypatch.setattr("sva.pipeline.make_default_perceiver", lambda: SimpleNamespace(model_id="dummy-vlm"))
    monkeypatch.setattr("sva.pipeline.make_default_interpreter", lambda: SimpleNamespace(model_id="dummy-llm"))
    monkeypatch.setattr("sva.pipeline.run_window", fake_run_window)
    monkeypatch.setattr("sva.pipeline.run_point", fake_run_point)
    monkeypatch.setattr("sva.pipeline.insert_event", fake_insert_event)
    monkeypatch.setattr("sva.pipeline._read_total_cost", lambda game_id: Decimal("1.23"))
    monkeypatch.setattr("sva.pipeline._mark_job_complete", lambda game_id: order.append("complete"))

    result = run_pipeline("tests/fixtures/cfr_baseline.mp4", game_id="game_test")

    assert result.events_inserted == 2
    assert result.observations == 2
    assert order.index("detect") < order.index("perceive:game_test:pt_001")
    assert order.index("detect") < order.index("perceive:game_test:pt_002")
    assert order.index("interpret:game_test:pt_001") < order.index("persist_event:game_test:pt_001")
    assert order.index("interpret:game_test:pt_002") < order.index("persist_event:game_test:pt_002")
    assert [event.point_id for event in inserted_events] == ["game_test:pt_001", "game_test:pt_002"]
    assert [event.point_ordinal for event in inserted_events] == [1, 2]
    assert [event.in_point_ts_ms for event in inserted_events] == [500, 999]
