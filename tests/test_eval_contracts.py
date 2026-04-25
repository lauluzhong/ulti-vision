"""Unit tests for Phase 7 gold-set contracts."""

from __future__ import annotations

import json

import pytest


def test_load_gold_manifest_rejects_unknown_event_game(tmp_path):
    from sva.eval.gold import load_gold_manifest

    manifest_path = tmp_path / "gold.json"
    manifest_path.write_text(
        json.dumps(
            {
                "dataset_id": "gold_v1",
                "games": [
                    {
                        "game_id": "game_a",
                        "source_video_ref": "fixtures/game_a.mp4",
                        "builder_labeler_id": "builder_1",
                        "independent_annotator_id": "annotator_2",
                    }
                ],
                "events": [
                    {
                        "gold_event_id": "gold_001",
                        "game_id": "game_missing",
                        "point_id": "game_missing:pt_001",
                        "point_ordinal": 1,
                        "video_ts_ms": 1000,
                        "in_point_ts_ms": 1000,
                        "type": "completion",
                        "team": "dark",
                        "labeler_id": "builder_1",
                    }
                ],
            }
        )
    )

    with pytest.raises(ValueError, match="unknown games"):
        load_gold_manifest(manifest_path)


def test_load_gold_manifest_accepts_valid_manifest(tmp_path):
    from sva.eval.gold import load_gold_manifest

    manifest_path = tmp_path / "gold.json"
    manifest_path.write_text(
        json.dumps(
            {
                "dataset_id": "gold_v1",
                "games": [
                    {
                        "game_id": "game_a",
                        "source_video_ref": "fixtures/game_a.mp4",
                        "builder_labeler_id": "builder_1",
                        "independent_annotator_id": "annotator_2",
                    }
                ],
                "events": [
                    {
                        "gold_event_id": "gold_001",
                        "game_id": "game_a",
                        "point_id": "game_a:pt_001",
                        "point_ordinal": 1,
                        "video_ts_ms": 1000,
                        "in_point_ts_ms": 1000,
                        "type": "completion",
                        "team": "dark",
                        "labeler_id": "builder_1",
                    }
                ],
            }
        )
    )

    manifest = load_gold_manifest(manifest_path)

    assert manifest.dataset_id == "gold_v1"
    assert manifest.full_games_total() == 1
    assert manifest.points_total() == 1
