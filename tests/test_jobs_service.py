"""Service-level tests for Phase 6 durable job orchestration."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from sva.jobs_dao import JobRecord
from sva.models import ModelMetadata, Observation
from sva.points.types import BoundarySignal, PointRecord


def _job_record(**overrides) -> JobRecord:
    base = JobRecord(
        game_id="game_async_001",
        video_id=None,
        status="queued",
        stage="queued",
        progress={
            "target_fps": 1,
            "points_total": 0,
            "points_completed": 0,
            "windows_total": 0,
            "windows_completed": 0,
            "events_inserted": 0,
        },
        error_message=None,
        cost_usd=Decimal("0"),
        source_path=str(Path("tests/fixtures/cfr_baseline.mp4").resolve()),
        source_kind="local_file",
        source_url=None,
        duration_s=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    return replace(base, **overrides)


def test_submit_local_job_creates_queued_job(monkeypatch, tmp_path):
    from sva.jobs_service import submit_local_job

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake")
    captured = {}

    def fake_upsert_job(**kwargs):
        captured.update(kwargs)
        return _job_record(
            game_id=kwargs["game_id"],
            progress=kwargs["progress"],
            source_path=kwargs["source_path"],
            source_kind=kwargs["source_kind"],
        )

    monkeypatch.setattr("sva.jobs_service.upsert_job", fake_upsert_job)

    record = submit_local_job(clip, game_id="game_submit_001", target_fps=2)

    assert record.game_id == "game_submit_001"
    assert captured["status"] == "queued"
    assert captured["stage"] == "queued"
    assert captured["source_kind"] == "local_file"
    assert captured["progress"]["target_fps"] == 2


def test_process_job_skips_points_with_existing_events_and_completes_remaining_work(monkeypatch):
    from sva.jobs_service import process_job
    from sva.models import DiscObservation, Event, PlayerCounts, SceneObservation
    from sva.ingest.ingest import IngestResult

    initial_job = _job_record()
    points_state: list[PointRecord] = []
    stage_updates: list[tuple[str | None, str | None, dict]] = []
    run_window_calls: list[str] = []
    inserted_events: list[str] = []

    ingested = IngestResult(
        video_id="vid_async_001",
        game_id="game_async_001",
        source_path=initial_job.source_path or "tests/fixtures/cfr_baseline.mp4",
        transcoded_path="/tmp/vid_async_001.mp4",
        duration_s=4.0,
        status="ingested",
        windows=[(0, 1000), (1001, 2000)],
        source_metadata=SimpleNamespace(duration_s=4.0),
        transcoded_metadata=SimpleNamespace(duration_s=4.0),
        source_kind="local_file",
        source_url=None,
    )

    points = [
        PointRecord(
            point_id="game_async_001:pt_001",
            game_id="game_async_001",
            point_ordinal=1,
            start_video_ts_ms=0,
            end_video_ts_ms=1000,
            confidence=0.9,
            boundary_evidence=[BoundarySignal(source="pull", video_ts_ms=0, confidence=0.9)],
        ),
        PointRecord(
            point_id="game_async_001:pt_002",
            game_id="game_async_001",
            point_ordinal=2,
            start_video_ts_ms=1001,
            end_video_ts_ms=2000,
            confidence=0.9,
            boundary_evidence=[BoundarySignal(source="scoreboard", video_ts_ms=1200, confidence=0.9)],
        ),
    ]

    def fake_upsert_job(**kwargs):
        progress = dict(kwargs.get("progress") or {})
        stage_updates.append((kwargs.get("status"), kwargs.get("stage"), progress))
        return _job_record(
            game_id=kwargs["game_id"],
            video_id="vid_async_001",
            status=kwargs.get("status", "running") or "running",
            stage=kwargs.get("stage", "queued") or "queued",
            progress=progress,
            cost_usd=Decimal("1.23"),
            source_path=initial_job.source_path,
            source_kind="local_file",
        )

    monkeypatch.setattr("sva.jobs_service.get_job", lambda game_id: initial_job)
    monkeypatch.setattr("sva.jobs_service.upsert_job", fake_upsert_job)
    monkeypatch.setattr("sva.jobs_service.ingest_local_file", lambda *args, **kwargs: ingested)
    monkeypatch.setattr("sva.jobs_service.list_points", lambda game_id: list(points_state))
    monkeypatch.setattr("sva.jobs_service.detect_points", lambda game_id, candidates: points)
    monkeypatch.setattr("sva.jobs_service.insert_points", lambda rows: points_state.extend(rows))
    monkeypatch.setattr(
        "sva.jobs_service.list_event_rows_for_point",
        lambda game_id, point_id: [object()] if point_id.endswith("pt_001") else [],
    )

    class DummyRetriever:
        async def retrieve(self, query):
            return []

    class DummyPerceiver:
        model_id = "dummy-vlm"

    monkeypatch.setattr("sva.jobs_service.MemoryRetriever", DummyRetriever)
    monkeypatch.setattr("sva.jobs_service.make_default_perceiver", lambda: DummyPerceiver())
    monkeypatch.setattr("sva.jobs_service.make_default_interpreter", lambda: SimpleNamespace(model_id="dummy-llm"))

    def fake_run_window(ctx, window, perceiver=None, on_cache_miss=None):
        _ = perceiver
        run_window_calls.append(window.window_id)
        observation = Observation(
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
        if on_cache_miss is not None:
            on_cache_miss(observation, "hash:test")
        return observation

    monkeypatch.setattr("sva.jobs_service.run_window", fake_run_window)
    monkeypatch.setattr("sva.jobs_service.insert_observations", lambda **kwargs: None)

    def fake_run_point(ctx, observations, interpreter=None, retrieved=None):
        _ = interpreter, retrieved
        return [
            Event(
                event_id=f"evt_{ctx.point_id}_goal",
                game_id=ctx.game_id,
                point_id=ctx.point_id or "missing",
                point_ordinal=ctx.point_ordinal or 0,
                video_ts_ms=observations[0].observation_ts_ms,
                in_point_ts_ms=0,
                type="goal",
                team="dark",
                model=ModelMetadata(provider="dummy", model_id="dummy-llm", version="test"),
            )
        ]

    monkeypatch.setattr("sva.jobs_service.run_point", fake_run_point)
    monkeypatch.setattr(
        "sva.jobs_service.insert_events",
        lambda events: inserted_events.extend(event.event_id for event in events),
    )

    result = process_job("game_async_001")

    assert run_window_calls == ["win_vid_async_001_1fps_1001_2000"]
    assert inserted_events == ["evt_game_async_001:pt_002_goal"]
    assert result.events_inserted == 1
    assert result.total_cost_usd == Decimal("1.23")
    assert [stage for _, stage, _ in stage_updates] == [
        "ingest",
        "point_detect",
        "persist",
        "perceive",
        "interpret",
        "persist",
        "complete",
    ]
    final_progress = stage_updates[-1][2]
    assert final_progress["points_completed"] == 2
    assert final_progress["windows_completed"] == 2
    assert final_progress["events_inserted"] == 1
