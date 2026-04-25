"""Tests for the Phase 7 eval gate wrapped around global memory promotion."""

from __future__ import annotations

from sva.eval.gate import evaluate_memory_promotion_gate
from sva.eval.harness import AlphaGateStatus, EvalReport
from sva.eval.metrics import EventMetric


def _metric(recall: float | None) -> EventMetric:
    return EventMetric(
        gold_count=10,
        predicted_count=10,
        true_positives=10 if recall is not None else 0,
        false_positives=0,
        false_negatives=0 if recall is not None else 10,
        precision=1.0 if recall is not None else None,
        recall=recall,
    )


def _report(
    *,
    dataset_ready: bool = True,
    completion_recall: float = 0.97,
    goal_recall: float = 1.0,
) -> EvalReport:
    metrics = {
        "completion": _metric(completion_recall),
        "goal": _metric(goal_recall),
    }
    return EvalReport(
        dataset_id="gold_v1",
        dataset_ready=dataset_ready,
        blocking_reasons=[] if dataset_ready else ["need real gold set"],
        full_games_total=3,
        points_total=40,
        independent_annotation_complete=dataset_ready,
        metrics_by_type=metrics,
        alpha_gate=AlphaGateStatus(
            ready=dataset_ready,
            blocked_reasons=[] if dataset_ready else ["need real gold set"],
            completion_recall=completion_recall,
            completion_precision=0.8 if dataset_ready else None,
            goal_recall=goal_recall,
            possession_change_recall=0.95 if dataset_ready else None,
        ),
    )


def test_memory_promotion_gate_blocks_without_eligible_gold_set():
    result = evaluate_memory_promotion_gate(
        _report(dataset_ready=False),
        _report(dataset_ready=False),
    )

    assert result.allowed is False
    assert any("eligible gold set" in reason for reason in result.blocked_reasons)


def test_memory_promotion_gate_blocks_recall_drop_of_three_points_or_more():
    result = evaluate_memory_promotion_gate(
        _report(completion_recall=0.97),
        _report(completion_recall=0.94),
    )

    assert result.allowed is False
    assert result.recall_deltas["completion"] == -0.03
    assert any("completion recall dropped by 0.030" in reason for reason in result.blocked_reasons)


def test_memory_promotion_gate_allows_small_non_regressing_change():
    result = evaluate_memory_promotion_gate(
        _report(completion_recall=0.97),
        _report(completion_recall=0.95),
    )

    assert result.allowed is True
    assert result.recall_deltas["completion"] == -0.02
