"""Gemini 2.5 Flash VLM adapter.

Calls the real Gemini File API with structured output keyed to the canonical
Observation schema. The prompt content lives in sva.perceive.prompt so any
VLM swap (Qwen2-VL, GPT-4V, etc.) reuses it without copy-paste.
"""

from __future__ import annotations

import mimetypes
import time
import uuid
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel

try:
    from google import genai
except ImportError:  # pragma: no cover - missing dependency in some dev envs
    genai = None  # type: ignore[assignment]

from sva.config import settings
from sva.models import MemoryRecord, ModelMetadata, Observation
from sva.observability import TraceContext, observe_call, prompt_version_hash
from sva.observability.cost import estimate_gemini_cost
from sva.perceive.adapters.base import PerceiveWindow
from sva.perceive.prompt import build_perceive_prompt

_MODEL_ID = "gemini-2.5-flash"
_VERSION = "v0-ultimate-aware-v1"
_MAX_RETRIES = 3
_BASE_BACKOFF_S = 0.25


def _get_client():
    if genai is None:
        raise RuntimeError("google-genai is not installed")
    return genai.Client(api_key=settings.gemini_api_key.get_secret_value())


def _full_prompt_text(
    window: PerceiveWindow,
    retrieved: list[MemoryRecord] | None,
) -> str:
    """Concatenated system+user prompt — used as the cache identity input."""
    system_prompt, user_prompt = build_perceive_prompt(window, retrieved=retrieved)
    return f"{system_prompt}\n\n{user_prompt}"


def _guess_mime_type(path: str) -> str:
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "video/mp4"


def _is_retryable_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True
    text = str(exc).lower()
    return any(token in text for token in ("rate limit", "resource exhausted", "429", "too many requests"))


def _usage_counts(response) -> tuple[int, int]:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return (0, 0)
    input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
    output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
    return (input_tokens, output_tokens)


def _parse_observation(response, window: PerceiveWindow, uploaded_file_name: str | None) -> Observation:
    parsed = getattr(response, "parsed", None)
    if parsed is None:
        raise ValueError("Gemini response did not include parsed Observation output")

    if isinstance(parsed, Observation):
        observation = parsed
    elif isinstance(parsed, BaseModel):
        observation = Observation.model_validate(parsed.model_dump(mode="json"))
    else:
        observation = Observation.model_validate(parsed)

    return observation.model_copy(
        update={
            "observation_id": observation.observation_id or f"obs_{uuid.uuid4().hex[:12]}",
            "window_id": window.window_id,
            "video_id": window.video_id,
            "video_ts_start_ms": window.video_ts_start_ms,
            "video_ts_end_ms": window.video_ts_end_ms,
            "observation_ts_ms": observation.observation_ts_ms or (
                (window.video_ts_start_ms + window.video_ts_end_ms) // 2
            ),
            "raw_response_ref": observation.raw_response_ref
            or getattr(response, "response_id", None)
            or uploaded_file_name,
            "model": ModelMetadata(
                provider="gemini",
                model_id=_MODEL_ID,
                version=getattr(response, "model_version", None) or _VERSION,
            ),
        }
    )


@observe_call(stage="perceive", model=_MODEL_ID)
def _call_gemini(
    ctx: TraceContext,
    window: PerceiveWindow,
    retrieved: list[MemoryRecord] | None = None,
) -> tuple[Observation, Decimal, int, int, TraceContext]:
    """Run one real Gemini perception call with bounded retry behavior."""
    client = _get_client()
    system_prompt, user_prompt = build_perceive_prompt(window, retrieved=retrieved)
    prompt_hash = prompt_version_hash(f"{system_prompt}\n\n{user_prompt}")
    started = time.monotonic()
    retry_count = 0
    uploaded = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            if uploaded is None:
                uploaded = client.files.upload(
                    file=Path(window.transcoded_path),
                    config=genai.types.UploadFileConfig(
                        displayName=window.window_id,
                        mimeType=_guess_mime_type(window.transcoded_path),
                    ),
                )
            response = client.models.generate_content(
                model=_MODEL_ID,
                contents=[uploaded, user_prompt],
                config=genai.types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=Observation,
                    temperature=0,
                ),
            )
            observation = _parse_observation(response, window, getattr(uploaded, "name", None))
            input_tokens, output_tokens = _usage_counts(response)
            cost = estimate_gemini_cost(input_tokens, output_tokens, model=_MODEL_ID)
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
                retry_count=retry_count,
                terminal_status="success",
            )
            return (observation, cost, input_tokens, output_tokens, updated_ctx)
        except Exception as exc:
            retry_count = attempt + 1
            if attempt >= _MAX_RETRIES or not _is_retryable_error(exc):
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
                    retry_count=retry_count,
                    terminal_status="retry_exhausted" if _is_retryable_error(exc) else "error",
                )
                # Return ctx details to observe_call via exception path by attaching them.
                exc.updated_ctx = updated_ctx  # type: ignore[attr-defined]
                raise
            time.sleep(_BASE_BACKOFF_S * (2**attempt))

    raise RuntimeError("Gemini perception unexpectedly exited retry loop")


class GeminiPerceiver:
    """Gemini 2.5 Flash perceiver using the swap-safe Observation contract."""

    model_id: str = _MODEL_ID
    provider: str = "gemini"

    def prompt_hash_for(
        self,
        window: PerceiveWindow,
        retrieved: list[MemoryRecord] | None = None,
    ) -> str:
        return prompt_version_hash(_full_prompt_text(window, retrieved))

    def perceive(
        self,
        ctx: TraceContext,
        window: PerceiveWindow,
        retrieved: list[MemoryRecord] | None = None,
    ) -> Observation:
        prompt_hash = self.prompt_hash_for(window, retrieved)
        enriched = TraceContext(
            stage="perceive",
            model=_MODEL_ID,
            video_id=ctx.video_id,
            game_id=ctx.game_id,
            window_id=window.window_id,
            point_id=ctx.point_id,
            point_ordinal=ctx.point_ordinal,
            prompt_version_hash=prompt_hash,
        )
        return _call_gemini(enriched, window, retrieved)


__all__ = ["GeminiPerceiver"]
