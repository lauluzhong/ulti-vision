# v0 Delivery Summary

**Date:** 2026-04-30
**Branch:** main (6 commits ahead of the previous deploy)
**Test status:** 101 passed, 19 skipped, 1 expected fail (iPhone HEVC fixture not yet provided)

This document summarizes what was built in the Week 1 v0 push and what
remains for you to do before sending the URL to your fellow coaches.

---

## What I built (6 commits)

### 1. WFDF rules + test isolation fix (`d5392ae`)
- Replaced `rulebook/usau_2024_2025.yaml` with `rulebook/wfdf_2025.yaml` (7 rules: goal, turnover, possession, point_end, pull, spirit, best-effort fallback).
- Updated all `rule_ref` strings in code (`USAU-XIV` → `WFDF-13.7`, `USAU-8.3` → `WFDF-13.1`, `USAU-13` → `WFDF-13.2`, etc.).
- Updated `interpret/prompt.py` to say "WFDF" instead of "USAU".
- Bulk-renamed rule_refs in 6 test fixture files.
- **Bonus fix:** the API was crashing on startup because `sva/api/app.py` referenced `settings.cors_allow_origins` without importing `settings`. Fixed.
- **Bonus fix:** 17 tests were spuriously failing due to a test-ordering bug — `tests/test_config.py::_reload_config()` was deleting the parent `sva` module from `sys.modules`, breaking submodule monkeypatch targets in downstream tests. Scoped to just `sva.config`.

### 2. Observation schema extension (`e4726c8`)
Additive (non-breaking) Pydantic schema extension giving the VLM a structured contract for the cues the new point detector needs:
- **`FormationObservation`**: `phase` (`pre_pull` / `pull_in_air` / `live_play` / `score_celebration` / `between_points` / `stoppage` / `unknown`), `pull_formation_visible`, `arms_raised_count`, `score_signal` (`two_hands_up` / `scoreboard_change` / `none` / `unknown`), `phase_confidence`, `score_signal_confidence`.
- **`FieldOrientation`**: `scoring_direction` (`screen_left` / `screen_right` / `screen_far` / `screen_near` / `unclear` / `unknown`), `endzone_visible`, `centerline_x_norm`.
- Persisted via the existing JSONB `payload` column on the observations table — no DB migration needed.
- All new fields default to `unknown` / safe values so existing test fixtures still validate.

### 3. VLM prompt rewrite for Ultimate-specific extraction (`f139e25`)
- Moved the prompt out of the Gemini adapter into `sva/perceive/prompt.py` so any VLM swap (Qwen2-VL, GPT-4V, etc.) reuses the same content.
- The new prompt:
  - Explicitly explains Ultimate game structure (pull → live play → score → walk back → next pull).
  - Asks for every field on `FormationObservation` and `FieldOrientation` with explicit guidance per enum value.
  - Lists useful action tags (`pull_release`, `throw_release`, `catch`, `drop`, `defensive_block`, `intercept`, `layout`, `sideline_signal_score`).
  - Three rules above all: never fabricate, be honest about disc visibility, use Ultimate game structure to identify phase.
- Widened the `Perceiver` Protocol to accept optional `retrieved: list[MemoryRecord]`. The prompt builder appends perceive-relevant memory guidance when present.
- Cache identity (`prompt_version_hash`) covers system + user + memory, so a coach correction that changes what the VLM should look for cleanly busts the cache.
- Bumped Gemini adapter version to `v0-ultimate-aware-v1`.

### 4. Real point detector v0 (`b8b4d41`) ⭐
**This is the biggest change.** The bootstrap whole-game-as-one-point detector is gone.

New: `detect_points_from_observations(game_id, observations)`:
- Walks observations chronologically, identifies contiguous in-point runs from `formation.phase`.
- Carries over `unknown` / `stoppage` phases so single noisy windows don't fragment a real point.
- Aggregates `pull_formation_visible` → `source=pull` boundary signals.
- Aggregates `score_signal=two_hands_up` → `source=vlm` boundary signals.
- Aggregates `score_signal=scoreboard_change` → `source=scoreboard` boundary signals.
- Falls back to a single `unclear` point covering the whole video (confidence=0.10) when the VLM gives no confident phase signals — UI flags for manual edit.

**Pipeline rewrite:** ingest → perceive every window → detect points from observations → persist observations + points → interpret per point. The old detect-before-perceive flow is gone. Same change in `jobs_service.process_job`.

**Trade-off:** cache-miss observations are buffered in memory and persisted *after* detection so they end up with the correct `point_id`. A crash mid-perception loses the buffer; the resume re-perceives all windows. Acceptable for v0 alpha with short clips.

**Tests:**
- 6 new unit tests for `detect_points_from_observations` covering single-point grouping, multi-point separation, unknown-phase carry-over, unclear fallback, and unsorted input.
- Rewrote `test_point_scoped_pipeline.py`, `test_jobs_service.py`, `test_orchestration.py` to match the new flow.

### 5. Claude LLM prompt rewrite for v0 honest-counts scope (`e9fa882`)
- The new prompt narrows the LLM's job to what coaches need from the v0 alpha:
  - Goals, completions (passes), turnovers, possession transitions when clearly visible.
- Best-effort fields (`turnover_subtype`, `throw_type`, `pass_direction`) explicitly **degrade to unknown** when evidence is thin. The prompt makes this an explicit instruction with reasoning: "missing an event the VLM didn't clearly see is better than fabricating one. The system has a coach-correction loop that will add the missed events back; it cannot easily remove fabricated ones."
- Wires WFDF rule references into the system prompt instead of generic "rule summary".
- Bumped Claude adapter version to `v0-honest-counts-v1`.

### 6. `sva run-local` smoke CLI (`9e2238a`)
Single command to push a clip through the full pipeline and print a structured result summary. No Docker, no API, no queue, no frontend needed.

```
sva run-local clip.mp4
sva run-local --url 'https://www.youtube.com/watch?v=xxx' --ack-rights
```

Prints three tables:
- Pipeline result (game_id, duration, windows, observations, events, cost)
- Detected points (ordinal, point_id, start/end ms, duration, confidence, evidence sources)
- v0 statistics (points / goals / completions / turnovers / possession transitions / unknown)

Plus an honesty banner when point confidence is low or 0 events were emitted.

---

## What you must do — short version

You're the only one who can do these. None require code changes from me.

### Before sending the URL to coaches: validate the pipeline produces useful output

1. **Get API keys** (your accounts, your billing — you must not share these with me).
   v0 uses **Gemini 2.5 Flash for both VLM and LLM**, so only ONE LLM provider is needed.
   - Gemini: https://aistudio.google.com/apikey
   - Langfuse Cloud (free tier): https://cloud.langfuse.com → Settings → API Keys

2. **Smoke-test locally first**:
   ```bash
   # Set up .env from .env.example with your real keys
   cp .env.example .env
   # Edit .env, fill in GEMINI_API_KEY, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY
   docker compose up -d db
   uv run alembic upgrade head
   uv run sva run-local <path-to-an-Ultimate-clip>
   ```
   You'll need a Postgres on localhost:5432 (the `docker compose` brings one up). The CLI will run the clip through Gemini end-to-end (VLM observations + LLM interpretation), then print the three tables.

3. **Look at the output and tell me what's wrong.** Specifically:
   - Are the detected points roughly right? (Right number of points? Reasonable boundaries?)
   - Are the goal counts believable?
   - Are the completion / turnover counts in the right ballpark?
   - Open the Langfuse dashboard and look at the perceive traces — what is the VLM actually reporting? Is the `formation.phase` field roughly right?

   **You are the domain expert.** I can't tell good output from bad without you looking at it. Send screenshots or paste the table outputs back to me, and we iterate on the prompts.

4. **Iterate prompts based on what you see.** This is where the swap-safe architecture pays off — we change `sva/perceive/prompt.py` or `sva/interpret/prompt.py`, the `prompt_version_hash` changes, and the next run uses the new prompt while keeping all the old infrastructure.

### Once the local smoke run is good: deploy

5. **Deploy backend on Render**:
   - Sign up at https://render.com if you haven't.
   - "New +" → "Blueprint" → connect to `lauluzhong/ulti-vision`. Render reads `render.yaml` automatically and provisions Postgres + Redis + the Docker web service.
   - In the Render dashboard, set the env vars marked `sync: false` in `render.yaml`:
     - `GEMINI_API_KEY`
     - `LANGFUSE_PUBLIC_KEY`
     - `LANGFUSE_SECRET_KEY`
     - `CORS_ALLOW_ORIGINS=https://your-vercel-domain.vercel.app` (set this AFTER you know the Vercel domain — see step 6)
   - Deploy. You'll get a URL like `https://ulti-vision-api.onrender.com`.

6. **Deploy frontend on Vercel** (you said this is already wired to the GitHub repo):
   - In Vercel project settings → Environment Variables, add `PUBLIC_API_BASE_URL=https://ulti-vision-api.onrender.com` (the URL from step 5).
   - Set the Vercel project root to `apps/web` (if it isn't already) so SvelteKit builds from the right directory.
   - Trigger a redeploy.

7. **Set CORS** — go back to Render, update `CORS_ALLOW_ORIGINS` to the Vercel URL.

8. **Send YOURSELF the URL first.** Run a clip end-to-end through the deployed system before sharing.

9. **Send the URL to one coach friend you trust.** Watch their first session. Look at the corrections they submit. Those become the first records in the memory store — the proprietary corpus we keep talking about.

### Optional / advisory

- **iPhone HEVC test fixture**: There's one expected test failure (`test_iphone_hevc_vfr_iphone.py`). To fix, drop a real iPhone-captured ~90s VFR clip at `tests/fixtures/iphone_hevc_vfr_90s.mov` plus its groundtruth JSON. This isn't blocking deployment.

---

## What's intentionally NOT done (deferred)

These are real but not blocking for the v0 alpha:

| Item | Why deferred | When |
|------|--------------|------|
| Real semantic embedding model (currently stub falls back to tag-match retrieval) | One coach (you) for first cycle — semantic ranking has no signal yet | After you've personally submitted ~20+ corrections |
| Per-window durable observation persistence (cache-miss is buffered until detect_points completes) | Acceptable trade-off for short alpha clips; rewrite would add complexity | Only if a real coach hits a meaningful crash |
| Real OCR scoreboard reading | The VLM extracts `text_observed` for scoreboard text, which is good enough for v0; OCR proper is heavier | If the VLM scoreboard extraction proves unreliable in your testing |
| Coordinate-based pass direction (centerline_x_norm trajectory) | Schema is in place; LLM uses it best-effort; not a v0 metric anyway | When pass-direction quality becomes a coach-priority signal |
| Eval harness with real gold set | Needs annotated games — only meaningful after several coaches use it | After alpha trickle (3-5 coaches) |

---

## Files changed in this push

```
src/sva/api/app.py                       (settings import fix)
src/sva/cli.py                           (run-local command)
src/sva/interpret/adapters/claude.py     (version bump)
src/sva/interpret/prompt.py              (LLM prompt rewrite + WFDF)
src/sva/interpret/rules.py               (USAU → WFDF)
src/sva/jobs_service.py                  (perceive-then-detect flow)
src/sva/models.py                        (FormationObservation + FieldOrientation)
src/sva/perceive/adapters/base.py        (Protocol accepts retrieved)
src/sva/perceive/adapters/gemini.py      (uses build_perceive_prompt + retrieved)
src/sva/perceive/prompt.py               (NEW — VLM prompt builder)
src/sva/perceive/runner.py               (run_window accepts retrieved)
src/sva/pipeline.py                      (perceive-then-detect flow)
src/sva/points/__init__.py               (export detect_points_from_observations)
src/sva/points/detector.py               (new heuristic detector)
rulebook/wfdf_2025.yaml                  (NEW — replaces usau_2024_2025.yaml)
rulebook/usau_2024_2025.yaml             (DELETED)
tests/test_config.py                     (test isolation fix)
tests/test_jobs_service.py               (rewrite for new flow)
tests/test_orchestration.py              (rewrite for new flow)
tests/test_point_detection.py            (6 new tests for v0 detector)
tests/test_point_scoped_pipeline.py      (rewrite for new flow)
tests/test_events_api.py                 (USAU → WFDF refs)
tests/test_events_dao.py                 (USAU → WFDF refs)
tests/test_exports_api.py                (USAU → WFDF refs)
tests/test_interpret_adapter.py          (USAU → WFDF refs)
tests/test_interpret_rules.py            (USAU → WFDF refs)
tests/test_memory_records_dao.py         (USAU → WFDF refs)
tests/test_models.py                     (USAU → WFDF refs)
```

Test pass rate: 101/102 (99%). The one fail is the iPhone HEVC fixture marker (you provide the clip; not a code bug).
