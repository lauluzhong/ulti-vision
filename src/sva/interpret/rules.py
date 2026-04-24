"""Rule-data loader and deterministic validator backbone for Phase 4."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from sva.models import Event

RULEBOOK_PATH = Path(__file__).resolve().parents[3] / "rulebook" / "usau_2024_2025.yaml"


class RuleEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str
    category: str
    summary: str
    hard: bool = False


class Rulebook(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ruleset_id: str
    ruleset_name: str
    rules: list[RuleEntry] = Field(default_factory=list)


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    severity: Literal["hard", "warn"]
    rule_ref: str
    message: str


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool = True
    hard_violation: bool = False
    issues: list[ValidationIssue] = Field(default_factory=list)


@lru_cache(maxsize=1)
def load_rulebook(path: Path = RULEBOOK_PATH) -> Rulebook:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return Rulebook.model_validate(payload)


def rules_summary(limit: int = 5) -> str:
    book = load_rulebook()
    return "\n".join(f"- {rule.ref}: {rule.summary}" for rule in book.rules[:limit])


def validate_event(event: Event, timeline: list[Event]) -> ValidationResult:
    issues: list[ValidationIssue] = []
    latest = timeline[-1] if timeline else None

    if event.type == "point_end":
        if latest is None or latest.type != "goal":
            issues.append(
                ValidationIssue(
                    severity="hard",
                    rule_ref="USAU-XIV",
                    message="point_end requires a goal immediately before it in the validated timeline",
                )
            )
        elif latest.team != "unknown" and event.team != "unknown" and latest.team != event.team:
            issues.append(
                ValidationIssue(
                    severity="hard",
                    rule_ref="USAU-XIV",
                    message="point_end team must match the team on the immediately preceding goal",
                )
            )

    if event.type == "goal":
        if event.team in {"unknown", "none"}:
            issues.append(
                ValidationIssue(
                    severity="warn",
                    rule_ref="USAU-8.3",
                    message="goal should name the scoring team when evidence is sufficient",
                )
            )
        if latest is not None and latest.type in {"possession_start", "completion"}:
            if latest.team not in {"unknown", "none"} and event.team not in {"unknown", "none"} and latest.team != event.team:
                issues.append(
                    ValidationIssue(
                        severity="hard",
                        rule_ref="USAU-8.3",
                        message="goal team contradicts the active possessing team in the timeline",
                    )
                )

    if event.type == "possession_start" and latest is not None:
        if latest.type in {"possession_start", "completion"}:
            if latest.team not in {"unknown", "none"} and event.team not in {"unknown", "none"} and latest.team != event.team:
                issues.append(
                    ValidationIssue(
                        severity="hard",
                        rule_ref="USAU-13",
                        message="possession cannot flip teams without an intervening turnover or goal",
                    )
                )

    hard = any(issue.severity == "hard" for issue in issues)
    return ValidationResult(ok=not hard, hard_violation=hard, issues=issues)


__all__ = [
    "RULEBOOK_PATH",
    "RuleEntry",
    "Rulebook",
    "ValidationIssue",
    "ValidationResult",
    "load_rulebook",
    "rules_summary",
    "validate_event",
]
