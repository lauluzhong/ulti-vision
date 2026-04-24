"""Crash-resume regression tests for durable job orchestration."""

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
        game_id="game_resume_001",
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


def test_process_job_resume_reuses_cached_windows_after_crash(monkeypatch):
    from sva.jobs_service import process_job
    from sva.models import DiscObservation, Event, PlayerCounts, SceneObservation
    from sva.ingest.ingest import IngestResult

    initial_job = _job_record()
    cached_windows: set[str] = set()
    fresh_window_calls: list[str] = []
    cache_hit_windows: list[str] = []
    inserted_events: list[str] = []
    stage_updates: list[tuple[str | None, str | None]] = []
    crash_once = {"armed": True}

    ingested = IngestResult(
        video_id="vid_resume_001",
        game_id="game_resume_001",
        source_path=initial_job.source_path or "tests/fixtures/cfr_baseline.mp4",
        transcoded_path="/tmp/vid_resume_001.mp4",
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
            point_id="game_resume_001:pt_001",
            game_id="game_resume_001",
            point_ordinal=1,
            start_video_ts_ms=0,
            end_video_ts_ms=2000,
            confidence=0.9,
            boundary_evidence=[BoundarySignal(source="pull", video_ts_ms=0, confidence=0.9)],
        ),
    ]

    monkeypatch.setattr("sva.jobs_service.get_job", lambda game_id: initial_job)
    monkeypatch.setattr(
        "sva.jobs_service.upsert_job",
        lambda **kwargs: (
            stage_updates.append((kwargs.get("status"), kwargs.get("stage"))),
            _job_record(
                game_id=kwargs["game_id"],
                video_id="vid_resume_001",
                status=kwargs.get("status", "running") or "running",
                stage=kwargs.get("stage", "queued") or "queued",
                progress=dict(kwargs.get("progress") or {}),
                source_path=initial_job.source_path,
                source_kind="local_file",
            ),
        )[1],
    )
    monkeypatch.setattr("sva.jobs_service.ingest_local_file", lambda *args, **kwargs: ingested)
    monkeypatch.setattr("sva.jobs_service.list_points", lambda game_id: points)
    monkeypatch.setattr("sva.jobs_service.detect_points", lambda game_id, candidates: points)
    monkeypatch.setattr("sva.jobs_service.insert_points", lambda rows: None)
    monkeypatch.setattr("sva.jobs_service.list_event_rows_for_point", lambda game_id, point_id: [])

    class DummyRetriever:
        async def retrieve(self, query):
            return []

    class DummyPerceiver:
        model_id = "dummy-vlm"

    monkeypatch.setattr("sva.jobs_service.MemoryRetriever", DummyRetriever)
    monkeypatch.setattr("sva.jobs_service.make_default_perceiver", lambda: DummyPerceiver())
    monkeypatch.setattr("sva.jobs_service.make_default_interpreter", lambda: SimpleNamespace(model_id="dummy-llm"))

    def fake_run_window(ctx, window, perceiver=None, on_cache_miss=None):
        _ = ctx, perceiver
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
        if window.window_id in cached_windows:
            cache_hit_windows.append(window.window_id)
            return observation
        fresh_window_calls.append(window.window_id)
        cached_windows.add(window.window_id)
        if on_cache_miss is not None:
            on_cache_miss(observation, "hash:test")
        if crash_once["armed"]:
            crash_once["armed"] = False
            raise RuntimeError("simulated crash after durable cache write")
        return observation

    monkeypatch.setattr("sva.jobs_service.run_window", fake_run_window)
    monkeypatch.setattr("sva.jobs_service.insert_observations", lambda **kwargs: None)
    monkeypatch.setattr(
        "sva.jobs_service.run_point",
        lambda ctx, observations, interpreter=None, retrieved=None: [
            Event(
                event_id="evt_resume_goal",
                game_id=ctx.game_id,
                point_id=ctx.point_id or "missing",
                point_ordinal=ctx.point_ordinal or 0,
                video_ts_ms=observations[-1].observation_ts_ms,
                in_point_ts_ms=0,
                type="goal",
                team="dark",
                model=ModelMetadata(provider="dummy", model_id="dummy-llm", version="test"),
            )
        ],
    )
    monkeypatch.setattr(
        "sva.jobs_service.insert_events",
        lambda events: inserted_events.extend(event.event_id for event in events),
    )

    try:
        process_job("game_resume_001")
    except RuntimeError as exc:
        assert "simulated crash" in str(exc)
    else:
        raise AssertionError("expected first run to crash")

    result = process_job("game_resume_001")

    assert fresh_window_calls == [
        "win_vid_resume_001_1fps_0_1000",
        "win_vid_resume_001_1fps_1001_2000",
    ]
    assert cache_hit_windows == ["win_vid_resume_001_1fps_0_1000"]
    assert inserted_events == ["evt_resume_goal"]
    assert result.events_inserted == 1
    assert stage_updates[-1] == ("complete", "complete")
