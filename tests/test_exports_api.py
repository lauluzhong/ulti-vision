"""Tests for Phase 6 CSV exports API."""

from __future__ import annotations

import csv
import importlib
from io import StringIO
from types import SimpleNamespace

import pytest

from sva.jobs_dao import JobRecord

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient


def _job() -> JobRecord:
    from datetime import datetime, timezone
    from decimal import Decimal

    return JobRecord(
        game_id="game_export_001",
        video_id="vid_export_001",
        status="complete",
        stage="complete",
        progress={"points_total": 2, "points_completed": 2},
        error_message=None,
        cost_usd=Decimal("0.22"),
        source_path="tests/fixtures/cfr_baseline.mp4",
        source_kind="local_file",
        source_url=None,
        duration_s=90.0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _event(
    event_id: str,
    *,
    point_id: str,
    point_ordinal: int,
    video_ts_ms: int,
    in_point_ts_ms: int,
    event_type: str,
    team: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        event_id=event_id,
        game_id="game_export_001",
        point_id=point_id,
        point_ordinal=point_ordinal,
        video_ts_ms=video_ts_ms,
        in_point_ts_ms=in_point_ts_ms,
        type=event_type,
        team=team,
        turnover_subtype=None,
        throw_type="backhand",
        pass_direction="lateral",
        prompt_version_hash="hash_hidden",
        details={"source": "canonical"},
        schema_version="1.0",
        source_observations=["obs_hidden"],
        rule_refs=["WFDF-1"],
        memory_refs=["mem_hidden"],
        confidence=0.91,
        warnings=[],
    )


def test_exports_api_returns_csv_one_row_per_event(monkeypatch):
    from sva.api.app import create_app

    api_module = importlib.import_module("sva.api.app")
    exports_module = importlib.import_module("sva.exports")
    monkeypatch.setattr(api_module, "get_job", lambda game_id: _job())
    monkeypatch.setattr(
        exports_module,
        "list_event_rows",
        lambda game_id: [
            _event(
                "evt_001",
                point_id="game_export_001:pt_001",
                point_ordinal=1,
                video_ts_ms=1000,
                in_point_ts_ms=1000,
                event_type="completion",
                team="dark",
            ),
            _event(
                "evt_002",
                point_id="game_export_001:pt_002",
                point_ordinal=2,
                video_ts_ms=8000,
                in_point_ts_ms=1200,
                event_type="goal",
                team="light",
            ),
        ],
    )

    client = TestClient(create_app())
    response = client.get("/exports/game_export_001.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(StringIO(response.text)))
    assert len(rows) == 2
    assert rows[0]["event_type"] == "completion"
    assert rows[1]["event_type"] == "goal"


def test_exports_api_header_order_is_stable_and_excludes_internal_fields(monkeypatch):
    from sva.api.app import create_app

    api_module = importlib.import_module("sva.api.app")
    exports_module = importlib.import_module("sva.exports")
    monkeypatch.setattr(api_module, "get_job", lambda game_id: _job())
    monkeypatch.setattr(exports_module, "list_event_rows", lambda game_id: [])

    client = TestClient(create_app())
    response = client.get("/exports/game_export_001.csv")

    header = response.text.splitlines()[0]
    assert header == (
        "export_version,game_id,point_id,point_ordinal,video_ts_ms,in_point_ts_ms,"
        "event_type,team,turnover_subtype,throw_type,pass_direction,confidence"
    )
    assert "event_id" not in header
    assert "memory_refs" not in header
    assert "prompt_version_hash" not in header
    assert "source_observations" not in header


def test_exports_api_rows_use_user_facing_sliceable_columns(monkeypatch):
    from sva.api.app import create_app

    api_module = importlib.import_module("sva.api.app")
    exports_module = importlib.import_module("sva.exports")
    monkeypatch.setattr(api_module, "get_job", lambda game_id: _job())
    monkeypatch.setattr(
        exports_module,
        "list_event_rows",
        lambda game_id: [
            _event(
                "evt_010",
                point_id="game_export_001:pt_003",
                point_ordinal=3,
                video_ts_ms=15500,
                in_point_ts_ms=2500,
                event_type="turnover",
                team="dark",
            )
        ],
    )

    client = TestClient(create_app())
    response = client.get("/exports/game_export_001.csv")

    row = list(csv.DictReader(StringIO(response.text)))[0]
    assert row["point_id"] == "game_export_001:pt_003"
    assert row["point_ordinal"] == "3"
    assert row["event_type"] == "turnover"
    assert row["team"] == "dark"
