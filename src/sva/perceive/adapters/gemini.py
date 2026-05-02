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
_VERSION = "v0-deterministic-fact-output-v2"
_MAX_RETRIES = 3
_BASE_BACKOFF_S = 0.25

# Frames-per-second Gemini extracts FROM each window's video slice for inference.
# We set this EXPLICITLY so motion-direction and event-transition observations
# are reliable; the SDK default is 1.0 which is too sparse for 2-second windows.
# 4.0 gives ~8 frames per 2-sec window — captures sub-second throw/catch
# transitions that 2.0 was missing (smoke test undercounted throws because
# a fast handoff < 0.5s fit entirely between fps=2 frame samples).
_VIDEO_INFERENCE_FPS = 4.0


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


def _wait_for_file_active(client, uploaded, timeout_s: float = 60.0, poll_interval_s: float = 1.0) -> None:
    """Block until Gemini's File API marks the upload as ACTIVE.

    Video uploads start in PROCESSING state and transition to ACTIVE when ready.
    Calling generate_content before ACTIVE returns 400 FAILED_PRECONDITION.
    Raises RuntimeError if the file enters FAILED state or times out.
    """
    deadline = time.monotonic() + timeout_s
    file_name = getattr(uploaded, "name", None)
    if file_name is None:
        return  # Nothing to poll; assume the SDK already returned a usable handle.

    while True:
        state = getattr(uploaded, "state", None)
        # The SDK exposes state as either an enum (with .name) or a string.
        state_str = getattr(state, "name", None) or str(state) if state is not None else "UNKNOWN"
        if state_str == "ACTIVE":
            return
        if state_str == "FAILED":
            raise RuntimeError(f"Gemini file upload entered FAILED state: {file_name}")
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"Gemini file upload did not reach ACTIVE within {timeout_s}s: "
                f"name={file_name} state={state_str}"
            )
        time.sleep(poll_interval_s)
        # Re-fetch state.
        try:
            uploaded = client.files.get(name=file_name)
        except Exception:
            # Transient error refreshing state — keep polling until deadline.
            pass


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
    """Parse a Gemini response into an Observation.

    Tries `response.parsed` first (when response_schema was honored), then falls
    back to `response.text` JSON. We don't pass response_schema directly because
    the google-genai SDK's schema-conversion currently emits Pydantic-style
    `additional_properties` that Gemini's REST API rejects (HTTP 400).
    Validating manually with Pydantic post-receipt gives us the same safety.
    """
    import json

    parsed = getattr(response, "parsed", None)
    if parsed is None:
        raw_text = getattr(response, "text", "") or ""
        if not raw_text:
            raise ValueError("Gemini response had no parsed payload and no text body")
        parsed = json.loads(raw_text)

    if isinstance(parsed, Observation):
        observation = parsed
    elif isinstance(parsed, BaseModel):
        observation = Observation.model_validate(parsed.model_dump(mode="json"))
    else:
        observation = Observation.model_validate(parsed)

    return observation.model_copy(
        update={
            # Always force a fresh, unique observation_id. The LLM has no business
            # inventing system IDs — when it does (e.g., Gemini takes a prompt
            # placeholder literally), every window collides on the same ID and
            # the unique constraint fires. Pipeline-side ID generation guarantees
            # uniqueness regardless of what the model returns.
            "observation_id": f"obs_{uuid.uuid4().hex[:12]}",
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
    *,
    uploaded: object,
) -> tuple[Observation, Decimal, int, int, TraceContext]:
    """Run one Gemini perception call against a PRE-UPLOADED file with time slicing.

    The upload is hoisted up to GeminiPerceiver._ensure_uploaded so the same
    52MB clip isn't reuploaded once per window. Each call here only sends a
    file reference + a video_metadata time slice, which costs ~26x fewer
    video tokens (only the 2-second window's frames are billed).
    """
    client = _get_client()
    system_prompt, user_prompt = build_perceive_prompt(window, retrieved=retrieved)
    prompt_hash = prompt_version_hash(f"{system_prompt}\n\n{user_prompt}")
    started = time.monotonic()
    retry_count = 0

    # Build the per-window content: file reference + video time slice + text prompt.
    # video_metadata.fps is set EXPLICITLY (not relying on Gemini's default 1.0)
    # so motion direction within a 2-second window can be detected. fps=2.0
    # gives 4 frames per 2-sec window — enough for direction/state-transition
    # judgement, still well under the 5 fps Gemini ceiling, and bills modestly.
    start_offset_s = window.video_ts_start_ms / 1000.0
    end_offset_s = window.video_ts_end_ms / 1000.0
    contents = [
        genai.types.Content(
            role="user",
            parts=[
                genai.types.Part(
                    file_data=genai.types.FileData(
                        file_uri=getattr(uploaded, "uri", None),
                        mime_type=getattr(uploaded, "mime_type", None) or _guess_mime_type(window.transcoded_path),
                    ),
                    video_metadata=genai.types.VideoMetadata(
                        start_offset=f"{start_offset_s:.2f}s",
                        end_offset=f"{end_offset_s:.2f}s",
                        fps=_VIDEO_INFERENCE_FPS,
                    ),
                ),
                genai.types.Part(text=user_prompt),
            ],
        ),
    ]

    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=_MODEL_ID,
                contents=contents,
                config=genai.types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    # Note: response_schema=Observation triggers an SDK bug
                    # (google-genai 1.73 emits `additional_properties` that
                    # Gemini's REST rejects). The system+user prompt describes
                    # the Observation shape; we Pydantic-validate post-receipt.
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
    """Gemini 2.5 Flash perceiver using the swap-safe Observation contract.

    Uploads each unique transcoded video to the Gemini File API ONCE per
    perceiver instance, then reuses that file reference across every window's
    perceive() call with a video_metadata time slice. This is dramatically
    cheaper than re-uploading per window (52 windows × 52s clip = ~26x video
    token savings) and faster (one ~5s upload instead of 52).
    """

    model_id: str = _MODEL_ID
    provider: str = "gemini"

    def __init__(self) -> None:
        # Cache: transcoded_path -> uploaded file reference (kept ACTIVE).
        # Lives on the perceiver instance so one pipeline run shares uploads
        # across all its windows; multiple pipeline runs each create their
        # own perceiver so caches don't leak across game_ids.
        import threading as _t

        self._upload_cache: dict[str, object] = {}
        self._upload_lock = _t.Lock()

    def _ensure_uploaded(self, transcoded_path: str) -> object:
        # Fast path: cache hit without lock.
        cached = self._upload_cache.get(transcoded_path)
        if cached is not None:
            return cached
        # Slow path: serialize uploads so 8 parallel perceivers don't trigger
        # 8 separate uploads of the same 100MB clip. Double-checked locking.
        with self._upload_lock:
            cached = self._upload_cache.get(transcoded_path)
            if cached is not None:
                return cached
            client = _get_client()
            uploaded = client.files.upload(
                file=Path(transcoded_path),
                config=genai.types.UploadFileConfig(
                    displayName=Path(transcoded_path).name,
                    mimeType=_guess_mime_type(transcoded_path),
                ),
            )
            # Block until ACTIVE — generate_content fails 400 FAILED_PRECONDITION
            # if called while the file is still PROCESSING.
            _wait_for_file_active(client, uploaded)
            # Refresh the handle once more so .uri / .state reflect ACTIVE.
            try:
                uploaded = client.files.get(name=getattr(uploaded, "name", None))
            except Exception:
                pass
            self._upload_cache[transcoded_path] = uploaded
            return uploaded

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
        uploaded = self._ensure_uploaded(window.transcoded_path)
        return _call_gemini(enriched, window, retrieved, uploaded=uploaded)


__all__ = ["GeminiPerceiver"]
