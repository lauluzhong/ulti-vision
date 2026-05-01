"""Unit tests for the Phase 7 eval harness."""

from __future__ import annotations

import json

def test_run_eval_reports_blocked_state_for_incomplete_real_gold_set(tmp_path):
    from sva.eval.harness import run_eval

    manifest_path = tmp_path / "gold.json"
    predictions_path = tmp_path / "predictions.json"

    manifest_path.write_text(
        json.dumps(
            {
                "dataset_id": "gold_v1",
                "games": [
                    {
                        "game_id": "game_a",
                        "source_video_ref": "fixtures/game_a.mp4",
                        "builder_labeler_id": "builder_1",
                        "independent_annotator_id": None,
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
    predictions_path.write_text(
        json.dumps(
            [
                {
                    "event_id": "evt_001",
                    "game_id": "game_a",
                    "point_id": "game_a:pt_001",
                    "point_ordinal": 1,
                    "video_ts_ms": 1100,
                    "in_point_ts_ms": 1100,
                    "type": "completion",
                    "team": "dark",
                }
            ]
        )
    )

    report = run_eval(manifest_path, predictions_path=predictions_path)

    assert report.dataset_ready is False
    assert report.alpha_gate.ready is False
    assert any("full games" in reason for reason in report.blocking_reasons)
    assert any("labeled points" in reason for reason in report.blocking_reasons)
    assert any("independent annotator" in reason for reason in report.blocking_reasons)
    assert report.metrics_by_type["completion"].true_positives == 1
