"""Gemini 2.5 Flash LLM interpreter adapter.

Uses the same google.genai client as the perceive stage — text in, structured
Event[] out. Lives behind the Interpreter Protocol so any LLM swap (DeepSeek,
GPT-4o-mini, Kimi K2, MiniMax, etc.) is one new file plus one edited line in
sva/interpret/runner.py::make_default_interpreter().

Why Gemini for v0:
- Same provider as the VLM stage = one less API key for the user
- Strong native structured-output support via response_schema (Pydantic types)
- ~20x cheaper per call than Claude Sonnet for this commodity-LLM task
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, TypeAdapter

try:
    from google import genai
except ImportError:  # pragma: no cover - missing dependency in some dev envs
    genai = None  # type: ignore[assignment]

from sva.config import settings
from sva.interpret.prompt import build_interpret_prompt
from sva.models import Event, MemoryRecord, ModelMetadata, Observation
from sva.observability import TraceContext, observe_call, prompt_version_hash
from sva.observability.cost import estimate_gemini_cost

_MODEL_ID = "gemini-2.5-flash"
_VERSION = "v0-gemini-honest-counts-v1"

_EVENTS_ADAPTER = TypeAdapter(list[Event])


def _get_client():
    if genai is None:
        raise RuntimeError("google-genai is not installed")
    return genai.Client(api_key=settings.gemini_api_key.get_secret_value())


def _usage_counts(response: Any) -> tuple[int, int]:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return (0, 0)
    return (
        int(getattr(usage, "prompt_token_count", 0) or 0),
        int(getattr(usage, "candidates_token_count", 0) or 0),
    )


def _parse_events(response: Any) -> list[Event]:
    """Try response.parsed first, fall back to response.text JSON parsing."""
    parsed = getattr(response, "parsed", None)
    if parsed is None:
        raw_text = getattr(response, "text", "") or ""
        if not raw_text:
            raise ValueError("Gemini response had no parsed payload and no text body")
        parsed = json.loads(raw_text)

    # Normalize to list of dicts before validating with the TypeAdapter.
    if isinstance(parsed, list):
        items: list[Any] = []
        for item in parsed:
            if isinstance(item, BaseModel):
                items.append(item.model_dump(mode="json"))
            else:
                items.append(item)
        return _EVENTS_ADAPTER.validate_python(items)

    raise ValueError(f"Expected list of Event objects, got {type(parsed).__name__}")


def _normalize_event(
    event: Event,
    ctx: TraceContext,
    source_ids: list[str],
    retrieved_ids: list[str],
) -> Event:
    update: dict[str, Any] = {
        "prompt_version_hash": event.prompt_version_hash or ctx.prompt_version_hash,
        "point_id": event.point_id or ctx.point_id or f"{ctx.game_id}:pt_001",
        "point_ordinal": event.point_ordinal or ctx.point_ordinal or 1,
        "game_id": event.game_id or ctx.game_id,
        "source_observations": event.source_observations or source_ids,
        "rule_refs": event.rule_refs,
        "memory_refs": event.memory_refs or retrieved_ids,
        "model": ModelMetadata(provider="gemini", model_id=_MODEL_ID, version=_VERSION),
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
def _call_gemini_interpret(
    ctx: TraceContext,
    observations: list[Observation],
    retrieved: list[MemoryRecord],
) -> tuple[list[Event], Decimal, int, int, TraceContext]:
    """Run one Gemini interpret call with structured JSON output."""
    client = _get_client()
    system_prompt, user_prompt = build_interpret_prompt(observations, retrieved)
    prompt_hash = prompt_version_hash(f"{system_prompt}\n\n{user_prompt}")
    started = time.monotonic()
    try:
        response = client.models.generate_content(
            model=_MODEL_ID,
            contents=[user_prompt],
            config=genai.types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=list[Event],
                temperature=0,
            ),
        )
        input_tokens, output_tokens = _usage_counts(response)
        cost = estimate_gemini_cost(input_tokens, output_tokens, model=_MODEL_ID)
        events = _parse_events(response)
        source_ids = [obs.observation_id for obs in observations]
        retrieved_ids = [memory.memory_id for memory in retrieved]
        events = [_normalize_event(event, ctx, source_ids, retrieved_ids) for event in events]
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
        exc.updated_ctx = TraceContext(  # type: ignore[attr-defined]
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


class GeminiInterpreter:
    """Gemini 2.5 Flash interpreter using the canonical Event[] contract."""

    model_id: str = _MODEL_ID
    provider: str = "gemini"

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
        return _call_gemini_interpret(enriched, observations, retrieved)


__all__ = ["GeminiInterpreter"]
