"""Evaluation harness exports for Phase 7."""

from sva.eval.gate import (
    PromotionEvalGateResult,
    assert_memory_promotion_gate,
    evaluate_memory_promotion_gate,
)
from sva.eval.gold import ComparableEvent, GoldEvent, GoldGame, GoldManifest, load_gold_manifest
from sva.eval.harness import AlphaGateStatus, EvalPrediction, EvalReport, run_eval
from sva.eval.metrics import EventMetric, compute_event_metrics

__all__ = [
    "AlphaGateStatus",
    "ComparableEvent",
    "EvalPrediction",
    "EvalReport",
    "EventMetric",
    "GoldEvent",
    "GoldGame",
    "GoldManifest",
    "PromotionEvalGateResult",
    "assert_memory_promotion_gate",
    "compute_event_metrics",
    "evaluate_memory_promotion_gate",
    "load_gold_manifest",
    "run_eval",
]
