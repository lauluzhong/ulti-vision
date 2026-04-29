"""Tests for rule-data loading and deterministic interpret validation."""

from __future__ import annotations

from sva.interpret.rules import load_rulebook, rules_summary, validate_event
from sva.models import Event, ModelMetadata


def _event(event_id: str, event_type: str, team: str = "dark") -> Event:
    return Event(
        event_id=event_id,
        game_id="g1",
        point_id="g1:pt_001",
        point_ordinal=1,
        video_ts_ms=0,
        in_point_ts_ms=0,
        type=event_type,  # type: ignore[arg-type]
        team=team,  # type: ignore[arg-type]
        model=ModelMetadata(provider="anthropic", model_id="claude-sonnet-4-5", version="v1"),
    )


def test_rulebook_loads_from_repo_data():
    book = load_rulebook()
    assert book.ruleset_id == "wfdf_2025"
    assert any(rule.ref == "WFDF-13.1" for rule in book.rules)
    assert "WFDF-13.1" in rules_summary()


def test_validator_catches_possession_flip_without_turnover():
    timeline = [_event("e1", "possession_start", team="dark"), _event("e2", "completion", team="dark")]
    candidate = _event("e3", "possession_start", team="light")
    result = validate_event(candidate, timeline)
    assert result.hard_violation is True
    assert any(issue.rule_ref == "WFDF-13.2" for issue in result.issues)


def test_validator_catches_point_end_without_goal():
    result = validate_event(_event("e1", "point_end", team="dark"), [])
    assert result.hard_violation is True
    assert any(issue.rule_ref == "WFDF-13.7" for issue in result.issues)


def test_validator_warns_on_goal_with_unknown_team_but_fails_open():
    result = validate_event(_event("e1", "goal", team="unknown"), [])
    assert result.hard_violation is False
    assert result.ok is True
    assert any(issue.rule_ref == "WFDF-13.1" for issue in result.issues)
