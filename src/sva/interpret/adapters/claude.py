"""Claude Sonnet 4.5 LLM adapter.

Phase 1 scope: emit a minimal Event with type='unknown' and exercise the Langfuse trace path.
Phase 4 replaces the body with real anthropic SDK calls + rules composition + structured output.
"""

from __future__ import annotations

import json
import time
import uuid
from decimal import Decimal
from typing import Any

from pydantic import TypeAdapter

try:
    import anthropic
except ImportError:  # pragma: no cover - missing dependency in some dev envs
    anthropic = None  # type: ignore[assignment]

from sva.models import Event, MemoryRecord, ModelMetadata, Observation
from sva.observability import TraceContext, observe_call, prompt_version_hash
from sva.observability.cost import estimate_claude_cost
from sva.interpret.prompt import build_interpret_prompt
from sva.config import settings

_MODEL_ID = "claude-sonnet-4-5"
_VERSION = "phase4-native-v1"
_MAX_TOKENS = 1200

_EVENTS_ADAPTER = TypeAdapter(list[Event])


def _get_client():
    if anthropic is None:
        raise RuntimeError("anthropic SDK is not installed")
    return anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())


def _usage_counts(message: Any) -> tuple[int, int]:
    usage = getattr(message, "usage", None)
    if usage is None:
        return (0, 0)
    return (int(getattr(usage, "input_tokens", 0) or 0), int(getattr(usage, "output_tokens", 0) or 0))


def _extract_text_blocks(message: Any) -> str:
    content = getattr(message, "content", None) or []
    texts: list[str] = []
    for block in content:
        if getattr(block, "type", None) == "text":
            texts.append(getattr(block, "text", ""))
    return "\n".join(texts).strip()


def _normalize_event(event: Event, ctx: TraceContext, source_ids: list[str]) -> Event:
    update: dict[str, Any] = {
        "prompt_version_hash": event.prompt_version_hash or ctx.prompt_version_hash,
        "point_id": event.point_id or ctx.point_id or f"{ctx.game_id}:pt_001",
        "point_ordinal": event.point_ordinal or ctx.point_ordinal or 1,
        "game_id": event.game_id or ctx.game_id,
        "source_observations": event.source_observations or source_ids,
        "rule_refs": event.rule_refs,
        "memory_refs": event.memory_refs,
        "model": ModelMetadata(provider="anthropic", model_id=_MODEL_ID, version=_VERSION),
    }
    if event.type == "turnover" and event.turnover_subtype is None:
        update["turnover_subtype"] = "unknown"
    if event.type == "completion":
        if event.throw_type is None:
            update["throw_type"] = "unknown"
        if event.pass_direction is None:
            update["pass_direction"] = "unknown"
    return event.model_copy(update=update)


@observe_call(stage="interpret", model=_MODEL_ID)
def _call_claude(
    ctx: TraceContext,
    observations: list[Observation],
    retrieved: list[MemoryRecord],
) -> tuple[list[Event], Decimal, int, int, TraceContext]:
    """Run one real Claude interpretation call with structured JSON output."""
    client = _get_client()
    system_prompt, user_prompt = build_interpret_prompt(observations, retrieved)
    prompt_hash = prompt_version_hash(f"{system_prompt}\n\n{user_prompt}")
    started = time.monotonic()
    try:
        message = client.messages.create(
            model=_MODEL_ID,
            max_tokens=_MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=0,
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": _EVENTS_ADAPTER.json_schema(),
                }
            },
        )
        input_tokens, output_tokens = _usage_counts(message)
        cost = estimate_claude_cost(input_tokens, output_tokens, model=_MODEL_ID)
        raw_text = _extract_text_blocks(message)
        parsed = _EVENTS_ADAPTER.validate_python(json.loads(raw_text))
        source_ids = [obs.observation_id for obs in observations]
        events = [_normalize_event(event, ctx, source_ids) for event in parsed]
        updated_ctx = TraceContext(
            stage=ctx.stage,
            model=ctx.model,
            video_id=ctx.video_id,
            game_id=ctx.game_id,
            window_id=ctx.window_id,
            point_id=ctx.point_id,
            point_ordinal=ctx.point_ordinal,
            prompt_version_hash=prompt_hash,
            latency_ms=int((time.monotonic() - started) * 1000),
            retry_count=0,
            terminal_status="success",
        )
        return (events, cost, input_tokens, output_tokens, updated_ctx)
    except Exception as exc:
        exc.updated_ctx = TraceContext(
            stage=ctx.stage,
            model=ctx.model,
            video_id=ctx.video_id,
            game_id=ctx.game_id,
            window_id=ctx.window_id,
            point_id=ctx.point_id,
            point_ordinal=ctx.point_ordinal,
            prompt_version_hash=prompt_hash,
            latency_ms=int((time.monotonic() - started) * 1000),
            retry_count=0,
            terminal_status="validation_error" if isinstance(exc, (json.JSONDecodeError, ValueError)) else "error",
        )
        raise


class ClaudeInterpreter:
    """Claude Sonnet interpreter using the widened canonical Event[] contract."""

    model_id: str = _MODEL_ID
    provider: str = "anthropic"

    def prompt_hash_for(
        self,
        observations: list[Observation],
        retrieved: list[MemoryRecord],
    ) -> str:
        system_prompt, user_prompt = build_interpret_prompt(observations, retrieved)
        return prompt_version_hash(f"{system_prompt}\n\n{user_prompt}")

    def interpret(
        self,
        ctx: TraceContext,
        observations: list[Observation],
        retrieved: list[MemoryRecord],
    ) -> list[Event]:
        prompt_hash = self.prompt_hash_for(observations, retrieved)
        enriched = TraceContext(
            stage="interpret",
            model=_MODEL_ID,
            video_id=ctx.video_id,
            game_id=ctx.game_id,
            window_id=ctx.window_id,
            point_id=ctx.point_id,
            point_ordinal=ctx.point_ordinal,
            prompt_version_hash=prompt_hash,
        )
        return _call_claude(enriched, observations, retrieved)

__all__ = ["ClaudeInterpreter"]
