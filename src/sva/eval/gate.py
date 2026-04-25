"""Regression gate for global memory promotions."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from sva.eval.harness import EvalReport


class PromotionEvalGateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed: bool
    blocked_reasons: list[str] = Field(default_factory=list)
    recall_deltas: dict[str, float] = Field(default_factory=dict)


def _recall_for(report: EvalReport, event_type: str) -> float | None:
    metric = report.metrics_by_type.get(event_type)
    if metric is None or metric.recall is None:
        return None
    return float(metric.recall)


def evaluate_memory_promotion_gate(
    baseline_report: EvalReport,
    candidate_report: EvalReport,
    *,
    recall_drop_threshold: float = 0.03,
) -> PromotionEvalGateResult:
    blocked_reasons: list[str] = []
    recall_deltas: dict[str, float] = {}

    if baseline_report.dataset_id != candidate_report.dataset_id:
        blocked_reasons.append("baseline and candidate eval reports must use the same dataset_id")

    if not baseline_report.dataset_ready or not candidate_report.dataset_ready:
        blocked_reasons.append("global promotion requires an eligible gold set before eval gating can pass")

    event_types = sorted(
        set(baseline_report.metrics_by_type.keys()) | set(candidate_report.metrics_by_type.keys())
    )
    for event_type in event_types:
        baseline_recall = _recall_for(baseline_report, event_type)
        candidate_recall = _recall_for(candidate_report, event_type)
        if baseline_recall is None:
            continue
        if candidate_recall is None:
            blocked_reasons.append(f"candidate eval is missing recall for event type {event_type}")
            continue
        delta = round(candidate_recall - baseline_recall, 4)
        recall_deltas[event_type] = delta
        if baseline_recall - candidate_recall >= recall_drop_threshold:
            blocked_reasons.append(
                f"{event_type} recall dropped by {baseline_recall - candidate_recall:.3f}, "
                f"meeting or exceeding the {recall_drop_threshold:.3f} threshold"
            )

    return PromotionEvalGateResult(
        allowed=not blocked_reasons,
        blocked_reasons=blocked_reasons,
        recall_deltas=recall_deltas,
    )


def assert_memory_promotion_gate(
    baseline_report: EvalReport,
    candidate_report: EvalReport,
    *,
    recall_drop_threshold: float = 0.03,
) -> PromotionEvalGateResult:
    result = evaluate_memory_promotion_gate(
        baseline_report,
        candidate_report,
        recall_drop_threshold=recall_drop_threshold,
    )
    if not result.allowed:
        raise ValueError("; ".join(result.blocked_reasons))
    return result


__all__ = [
    "PromotionEvalGateResult",
    "assert_memory_promotion_gate",
    "evaluate_memory_promotion_gate",
]
