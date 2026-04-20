# Stack Research

**Domain:** Sports video analytics — VLM+LLM event-extraction pipeline for Ultimate Frisbee
**Researched:** 2026-04-20
**Confidence:** HIGH on pricing and model capability (verified against official docs 2026-04); MEDIUM on framework choices (ecosystem moves fast, verified against multiple 2026 sources); LOW on self-host cost projections (depend on GPU availability and quantization choices)

---

## TL;DR — Recommended Stack

| Layer | Primary Pick | Confidence |
|---|---|---|
| VLM (perception) | **Gemini 2.5 Flash** (primary) + **Gemini 2.5 Pro** for hard clips | HIGH |
| LLM (interpretation) | **Claude Sonnet 4.5** with prompt caching | HIGH |
| Orchestration | **Pydantic AI + plain Python async** (no LangGraph) | MEDIUM |
| Memory store | **SQLite + JSONL example bank** with **LanceDB** for semantic retrieval | MEDIUM |
| Video ingest | **yt-dlp** (dev only) + **PyAV** for frame extraction | HIGH |
| Backend | **FastAPI** 0.115+ on Python 3.12 | HIGH |
| Job queue | **Dramatiq** + Redis (escape hatch: Modal functions) | MEDIUM |
| Frontend | **SvelteKit** 2 with shadcn-svelte or daisyUI | MEDIUM |
| Hosting | **Fly.io** (API + worker) + **Modal** (GPU bursts when self-hosting VLM) | MEDIUM |
| Observability | **Langfuse Cloud** (free tier) with OpenTelemetry export | HIGH |
| Blob storage | **Cloudflare R2** (zero egress) | HIGH |

**Core thesis behind these picks:** every component is swappable. No framework that hides prompts (i.e., no LangChain). Cost discipline baked into the VLM layer because video is where the money goes. One-person-ops everywhere else.

---

## Recommended Stack — Detailed

### 1. VLM (perception layer)

| Technology | Version | Purpose | Why Recommended |
|---|---|---|---|
| **Gemini 2.5 Flash** | `gemini-2.5-flash` (GA) | Per-clip observation extraction at ~1 fps native sampling | Native video input, cheapest per-second-of-video of any frontier model, text/image/video all priced at $0.30/M input. Only model that accepts raw mp4 via File API and handles internal sampling, which eliminates a whole category of our frame-batching code. |
| **Gemini 2.5 Pro** | `gemini-2.5-pro` | Hard-clip reprocessing (confused possession, occlusion, crowded sidelines) | Same video pipeline as Flash, but smarter. $1.25/M input (≤200k ctx). Up to 2-hour video with 2M-ctx variant. Use as the "second opinion" on clips Flash flagged low-confidence. |

**Why Gemini and not GPT-4o/Claude for the VLM role:** Gemini is the only frontier API with first-class video input. GPT-4o and Claude require you to extract frames client-side, encode each as an image token, and manually interleave timestamps — that's more code, higher per-minute token count (every frame is billed as a full image), and you lose the model's native temporal reasoning. Gemini 2.5 Flash bills video at `~258-300 tokens/second` of source video at 1fps, which is *dramatically* cheaper than batching hand-extracted frames through any other provider.

**Per-game cost model (60-minute game):**

Scenario A — Gemini 2.5 Flash native video, 1 fps sampling (default):
- Video tokens: 60 min × 60 sec × 300 tok = 1.08M input tokens
- Per-clip prompting overhead (rules + schema reminder): ~2000 tok × ~120 clips = 240k tokens (heavily cache-hit after warmup)
- Output (structured observations): ~200 tok × 120 clips = 24k output tokens
- Cost: `1.08M × $0.30 + 0.24M × $0.30 (cold) + 0.024M × $2.50`
- **≈ $0.46 per game** uncached; **~$0.38 with prompt caching**

Scenario B — Gemini 2.5 Pro on the same game:
- Same token counts, priced at $1.25/$10.00
- **≈ $1.61 per game**

Scenario C — GPT-4o with 3fps manual frame extraction:
- 60 × 60 × 3 = 10,800 frames. Each frame consumed as an image tile (~255 image tokens low detail, ~1105 high detail).
- Low detail: 10,800 × 255 = 2.75M input tok → **~$6.88** (at $2.50/M) just for perception, ignoring prompt overhead.
- High detail: **~$29** per game.
- Not viable at cost-sensitive scale.

Scenario D — Claude Sonnet 4.5 with frame batches:
- Each image is ~1600 tokens typical. 3fps × 60min = 10.8k frames is prohibitive; even at 1fps that's ~5.8M tokens → **~$17+** per game. Not viable for perception.

**Rate limits (Tier 1 paid):** Gemini 2.5 Flash: 1000 RPM, 4M TPM — plenty for a solo dev processing dozens of games. Gemini 2.5 Pro: 360 RPM on paid tier.

**Open-source escape hatch (confidence: MEDIUM):**

| Model | Role | When to Flip |
|---|---|---|
| **Qwen2.5-VL-7B** (or Qwen3-VL) | Self-host on Modal/RunPod | If per-game cost exceeds budget at scale, or if privacy/IP becomes a concern |
| **Qwen2.5-VL-72B** | Heavier self-host alternative | Only if 7B recall isn't good enough and you have the GPU budget |

Qwen2.5-VL is the only open VLM class that credibly handles >1hr video with temporal grounding. Llama 3.2 Vision is image-only (no video temporal reasoning), so it's not a real substitute. Pixtral is image-strong but weaker on long video. InternVL2/3 is in the running but lags Qwen on video benchmarks as of early 2026.

**Do not plan self-host for prototype.** You want frontier quality during calibration so corrections are meaningful, not "is the model broken or is the rule wrong?" Revisit self-host after you have the gold set and a cost-per-game baseline.

---

### 2. LLM (interpretation layer)

| Technology | Version | Purpose | Why Recommended |
|---|---|---|---|
| **Claude Sonnet 4.5** | `claude-sonnet-4-5` | Reconcile VLM observations into canonical game events using rules + few-shot memory | Best-in-class structured output + tool use, excellent instruction following for rule-based reconciliation, **1M context window** lets you dump a point's worth of VLM observations + rules + ~50 few-shot examples in one call, and **prompt caching at 0.1x input price** makes the rules/examples free-ish after warm-up. |

**Cost model per game (120 points × 1 interpretation call each):**
- Prompt (rules + few-shot + schema): ~8k tokens, cached → 8k × $3 × 0.1/M = $0.0024/call cached (vs $0.024 uncached)
- VLM observation block per point: ~1k tokens → $0.003/call
- Output (structured event list): ~500 tokens → $0.0075/call
- **≈ $0.013 per point × 120 points = $1.56 per game** with caching; ~$4 without.

**Why Sonnet 4.5 and not Opus 4.7 for this role:**
- Opus 4.7 is 5x the output cost ($25/M vs $15/M) and only marginally better at structured-output rule following.
- Reserve Opus for eval/audit runs and for the correction review UI where the user explicitly wants the best.
- **Rule of thumb:** Sonnet for per-request inference, Opus for batch-correction/gold-label generation and hard-case audits.

**Runner-up: Gemini 2.5 Pro.** If you're already calling Gemini for the VLM, you save one vendor. But Sonnet 4.5 is measurably better at rule-following today, and 1M-context + 0.1x cache reads means it's cheap enough that the two-vendor split is worth it.

**Do not use GPT-4o for interpretation.** Structured-output compliance drifts more than Claude/Gemini in multi-rule scenarios, and caching is coarser.

---

### 3. Orchestration framework

| Technology | Version | Purpose | Why Recommended |
|---|---|---|---|
| **Pydantic AI** | ^0.0.40+ | Define Agent/tool contracts, handle structured outputs, swap providers via model string | Lowest lock-in of the serious options. A `pydantic_ai.Agent` is roughly: model + system prompt + output type + tools. Provider-swapping is a string change (`"google-gla:gemini-2.5-flash"` → `"anthropic:claude-sonnet-4-5"`). Structured output via Pydantic models is the exact shape you'll use everywhere else. |
| **Plain Python asyncio** | stdlib | Fan-out over clips, gather results, retry with tenacity | You're orchestrating two model calls per point. This doesn't need a graph framework. `asyncio.gather` + `tenacity` retry decorators handles it. |

**Why NOT LangGraph / LangChain:** LangChain's abstractions hide the prompt from you, which is fatal for a project where the whole thesis is "external memory = explicit prompt engineering that compounds." You *need* to see and control the exact bytes going to the model. LangGraph is fine for multi-agent workflows but this isn't one; it's a two-stage pipeline with retries. Adding a graph framework here adds abstraction debt with no benefit.

**Why NOT raw SDKs only:** The `google-genai` and `anthropic` SDKs are great, but without Pydantic AI you re-implement: retry-with-exponential-backoff, JSON-schema output coercion, provider switching. Pydantic AI is a thin, opinionated layer that saves exactly the code you don't want to maintain and never hides the prompt.

**Why NOT DSPy (yet):** DSPy is *interesting* for the memory layer (automatic few-shot optimization is attractive) but it inverts the control flow: DSPy wants to own prompt construction. That conflicts with "memory decoupled, models swappable, prompts inspectable." Revisit DSPy in a later phase as a specialized optimizer for the few-shot bank, not as the primary orchestrator. Keep it on the list as a v2 experiment.

Confidence: MEDIUM — Pydantic AI is young (pre-1.0). If it stalls, the migration path to raw SDKs is trivial because you own the prompts.

---

### 4. External memory store

| Technology | Version | Purpose | Why Recommended |
|---|---|---|---|
| **SQLite** | 3.45+ | Source-of-truth for rules, examples, corrections, events | Single-file, embedded, bulletproof. Already battle-tested for solo-dev projects at 10k-1M row scale. Use the `sqlite-vec` or `sqlite-vss` extension if you want vectors in the same DB. |
| **JSONL example bank** | — | Canonical few-shot store: one example per line, version-controlled | Git-friendly, grep-able, reviewable. Corrections land here as JSONL rows; retrieval just loads relevant rows into the Claude prompt. |
| **LanceDB** | 0.15+ | Semantic retrieval over examples ("find 5 examples most similar to this observation") | Embedded (no server), columnar, handles the "examples bank grows to 10k+" case without needing a vector DB server. Zero-ops for a solo dev. |

**Architecture note:** the memory store is the place where the "decoupled from model" requirement lives. Examples and rules are stored as *text + structured metadata*. When you swap the LLM from Claude to Gemini, you just change the prompt template that renders the example — the memory content is unchanged. This is why we do NOT use DSPy-optimized stored prompts as the primary memory (those bake in a specific model's tokenizer/style).

**Why NOT Chroma:** Chroma is fine, but LanceDB's single-file + Lance columnar format makes backups and versioning (commit to git LFS, snapshot to R2) one-liners. Chroma needs a running process and SQLite-for-metadata even in "persistent" mode. Less operational burden.

**Why NOT Qdrant:** Great for production search at scale, overkill for a solo-dev memory bank that'll be <100k examples for years. Adds a service to run.

**Why NOT Pinecone/Weaviate:** SaaS lock-in + monthly fee + cold-start latency on free tiers. Everything they do you can do locally at this scale.

**Why NOT "just put everything in the LLM context":** 1M context is tempting. Don't. You want *retrieval* so corrections to point-specific examples don't have to fit inside every prompt. Retrieval also gives you provenance — "this event was judged using examples X, Y, Z" is essential for the correction workflow.

---

### 5. Video handling

| Technology | Version | Purpose | Why Recommended |
|---|---|---|---|
| **yt-dlp** | latest (updated weekly) | Pull public YouTube / UFA stream URLs for dev/eval use | De facto standard; actively maintained; handles UFA's YouTube streams. Not for production user-facing ingestion. |
| **PyAV** | 13+ | Frame extraction, duration probe, HWAccel-aware decode | Python bindings to ffmpeg libraries directly (not subprocess). Frame-accurate seeking. Works fine without GPU; plugs into NVDEC/VideoToolbox if present. |
| **ffmpeg** | 6.x+ | Installed as a system dependency (PyAV needs it) | Standard install. Pin in Docker image. |

**Why NOT decord:** Decord is fast but its project activity slowed noticeably in 2023-2024 and it has known wheel/build issues on Python 3.12+. PyAV is less fancy but actively maintained and stable on macOS + Linux.

**Why NOT python-ffmpeg / ffmpeg-python subprocess wrappers:** They shell out to the `ffmpeg` binary for each operation. Fine for one-shot conversion; bad for frame-by-frame control and ~100x slower than PyAV for the frame-extraction loop you'll run thousands of times.

**Critical architectural decision — let Gemini do the sampling:** For v1, DO NOT extract frames locally and send them to Gemini. Upload the mp4 to Gemini's File API and let it sample natively. Frame extraction is only needed if you switch to GPT-4o/Claude/self-host VLM. This saves you: (a) frame-extraction code, (b) upload bandwidth of individual images, (c) billing for each frame as a full image. Keep PyAV in the stack anyway for: clip slicing (per-point windows), thumbnails, and the eventual self-host path.

**yt-dlp legality:** Downloading copyrighted YouTube content violates YouTube ToS (though yt-dlp itself is legal software). For dev use against public UFA streams the risk is low but non-zero. For production user-facing ingestion, do NOT use yt-dlp — require users to upload their own footage or own the rights. Make this a product constraint from day 1.

---

### 6. Backend framework

| Technology | Version | Purpose | Why Recommended |
|---|---|---|---|
| **FastAPI** | 0.115+ | HTTP API: upload endpoints, job status, event queries, correction submission | Largest Python ecosystem, best docs, native Pydantic integration (the same models we use for structured LLM output and memory). OpenAPI auto-gen for the frontend. Solo-maintainable. |
| **Pydantic** | 2.9+ | Data validation across API, LLM I/O, memory schemas | One type system end-to-end. |
| **uvicorn** | 0.32+ | ASGI server | Standard pairing. |

**Why NOT Litestar:** 2x synthetic perf advantage, but we are not serving high QPS — we're serving 1-50 requests/min from a handful of coaches. Litestar's smaller ecosystem costs more debugging hours than FastAPI's overhead costs in latency. Revisit only if we ever bottleneck on request throughput (unlikely for this product shape).

**Why NOT Hono/Bun or Node:** You'll be writing a ton of Python anyway (Pydantic AI, PyAV, job workers, ML libs). One language = half the context-switching cost for a solo dev. Only break this rule if you already live in TypeScript and hate Python.

---

### 7. Job queue (long-running video jobs)

| Technology | Version | Purpose | Why Recommended |
|---|---|---|---|
| **Dramatiq** | 1.17+ | Enqueue/run the "process this game" job out-of-process from the API | Modern Celery alternative. Simpler API, better defaults (automatic retries, dead-letter, rate-limiting), actively maintained, Redis broker keeps deps minimal. ~10x faster than RQ at scale. |
| **Redis** | 7.x | Broker + result backend | Also doubles as your job-status KV and cache. |

**Why Dramatiq over Celery:** Celery's config surface is enormous and half of it exists for Django/RabbitMQ patterns you don't need. Dramatiq was built by someone who said "Celery is too much" and did it right. For a solo dev, this matters — fewer Celery gotchas to debug at 11pm.

**Why Dramatiq over RQ:** RQ is simpler still, but its concurrency model (one job = one forked process) is painful for long jobs that want to be async internally (our VLM calls should fan out via `asyncio.gather` inside one job). Dramatiq supports async actors natively.

**Why NOT FastAPI `BackgroundTasks`:** These run in the same event loop as the API. A 10-minute video-processing job will starve your request handlers and won't survive a deploy/restart. Non-starter for this workload.

**Why NOT Celery:** See above, and the upgrade path if we ever need Celery's features is easy — Dramatiq's actor API maps cleanly.

**Why NOT Temporal/Inngest:** Nice tools, wrong size. Temporal is for durable multi-step workflows across services; Inngest is for event-driven systems. Adding either is taking on a platform commitment we don't need yet.

**Escape hatch — Modal serverless functions:** If you move the VLM step to self-host (Qwen2.5-VL on GPU), the cleanest architecture is: API + Dramatiq on Fly.io handle the non-GPU work; individual per-point VLM calls are `modal.Function.spawn()` invocations against a Modal GPU container that auto-scales to zero. Pay only for the GPU seconds used. This replaces the "run a RunPod pod and pray" pattern.

---

### 8. Frontend

| Technology | Version | Purpose | Why Recommended |
|---|---|---|---|
| **SvelteKit** | 2.x (Svelte 5 runes) | Upload UI, event list, stats dashboard, correction interface | Lowest-JS output of the "real framework" options, dev experience is fastest, solo-maintainable. Svelte 5's `$state` runes are intuitive for an interactive timeline UI. |
| **shadcn-svelte** or **daisyUI** | current | Component library | Copy-paste components, no heavy UI framework lock-in. |
| **@tanstack/table** (svelte adapter) | latest | Event table with sort/filter/edit-in-place for corrections | The only serious headless table lib that ports cleanly across frameworks if we ever rewrite. |
| **video.js** or native `<video>` | current | Timestamped deep-links from event list into video playback | video.js if you need plugins; raw `<video>` with time-seeking is often enough. |

**Why SvelteKit over Next.js for THIS project:** Minimal dashboards with interactive tables and a video timeline are exactly SvelteKit's sweet spot. Next.js' RSC + server actions complexity is overkill for a 5-route app. Ship-speed matters more than ecosystem here — all serious component libs (shadcn, tanstack, cmdk) now have Svelte ports.

**Why NOT HTMX + FastAPI templates:** Tempting for "minimal," but you'll want client-side state for the video timeline scrubber + live-updating correction form. HTMX makes that awkward. Use HTMX if the UI were genuinely forms-only; it isn't.

**Why NOT Astro:** Static-first. Our UI is app-like (auth, uploads, corrections, live job status). Wrong tool.

**Deployment path:** Build as static SPA + API calls (`adapter-static` or `adapter-node` depending on auth story). Host on Cloudflare Pages (free) or alongside the API on Fly.

---

### 9. Hosting

| Technology | Version | Purpose | Why Recommended |
|---|---|---|---|
| **Fly.io** | — | FastAPI + Dramatiq worker + Redis | Cheapest credible platform with first-class Docker, persistent volumes (for SQLite/LanceDB), global edge, GPU option if we ever want it, scale-to-zero for workers. Solo-dev ergonomics are excellent. ~$5-20/mo for the whole backend at alpha scale. |
| **Modal** | — | On-demand GPU for self-hosted VLM (Qwen2.5-VL) *if/when* we move off Gemini | Per-second billing, scale-to-zero, $30/mo free credit covers a lot of dev. A10 at $0.0003/sec (~$1.10/hr) is plenty for perception at our volume. |
| **Cloudflare Pages** | — | SvelteKit static build | Free tier, fast, easy DNS since R2 lives in the same account. |

**Why Fly.io over Railway:** Railway is slightly nicer UX but Fly has better Docker control, persistent-volume semantics for our SQLite/LanceDB files, and regional choice matters when we expand to multi-region. Either would work; Fly wins on flexibility. Runner-up.

**Why NOT Render:** Fine, but slower cold starts on free tier and volume pricing is worse than Fly for our shape.

**Why NOT AWS/GCP direct:** Too much ops for a solo dev in 2026. Use them via Fly/Modal/Cloudflare abstractions.

**Why NOT Vercel:** Good for the frontend if you want it; we already have Cloudflare Pages and Vercel's pricing cliffs for compute-heavy workloads aren't friendly.

**Critical Modal pricing note:** The advertised per-second rates apply to the default tier. If you scale to "production" multi-GPU concurrency, Modal applies tier multipliers that can ~3x the bill. Stay on the starter plan; the $30/mo free credit + pay-as-you-go is right for this product's shape until you have real volume.

---

### 10. Observability

| Technology | Version | Purpose | Why Recommended |
|---|---|---|---|
| **Langfuse Cloud** | Hobby tier (free 50k observations/mo) | Trace every VLM + LLM call with cost, latency, inputs/outputs | Open-source, MIT license (self-host option preserved for later), best-in-class cost-tracking per-model / per-user / per-feature. Critical for the "per-game cost visibility from day 1" requirement. |
| **OpenTelemetry** | 1.x | Generic app tracing (FastAPI + Dramatiq) | Standard. Langfuse imports OTel traces. |
| **Sentry** | — | Error reporting | Free tier is fine for alpha. |

**Why Langfuse over LangSmith:** LangSmith locks you into LangChain's mental model and pricing jumps fast. Langfuse is model-agnostic, self-hostable if you ever need data residency, and its per-trace cost breakdown is exactly the view you need for "what does Game X cost."

**Why NOT Phoenix (Arize):** Great for evals and drift, but its cost-tracking is weaker than Langfuse's and its killer feature is drift monitoring — not our primary problem in alpha.

**Why NOT Logfire:** Promising (same company as Pydantic, Pydantic AI integration is slick) but less mature cost-tracking than Langfuse. Re-evaluate in 6 months.

**Instrumentation pattern:** Wrap every VLM/LLM call with a Langfuse `@observe` decorator. Tag with `game_id`, `point_id`, `model`, `step=perception|interpretation`. Your dashboard answer to "how much did this game cost?" becomes a trivial Langfuse filter.

---

### 11. Storage for uploaded videos + generated event timelines

| Technology | Version | Purpose | Why Recommended |
|---|---|---|---|
| **Cloudflare R2** | — | Short-term video storage during processing; event JSON/CSV artifacts | S3-compatible, zero egress fees (critical when you stream the user's own video back to them), $0.015/GB/mo. We explicitly do NOT want to be a video host long-term — set 7-day lifecycle rules and delete. |
| **SQLite** (Fly volume) | 3.45+ | Event data, memory store, metadata | Already in the stack; no reason to split. |
| **boto3** or `aioboto3` | current | R2 client (S3-compatible) | Standard. |

**Why R2 over S3:** Egress. If a coach downloads their own 2GB game footage once, S3 bills you $0.18 per game for egress; R2 bills $0. At alpha scale this is rounding error, but it removes a decision you'd have to revisit at any scale.

**Why NOT Backblaze B2:** Slightly cheaper storage but egress is only free via the Cloudflare CDN partnership, which is more config than just-use-R2. If storage cost ever dominates (unlikely — videos auto-delete after 7 days), revisit.

**Why NOT Supabase Storage:** Supabase is great but you'd be paying for Postgres + storage + auth as a bundle. We want a la carte.

**Why NOT local disk only:** Fly.io volumes are fine for metadata but getting a 2GB upload onto the volume is painful compared to "user uploads directly to R2 via signed URL, worker reads from R2." Direct-to-R2 signed uploads also bypass your FastAPI process entirely for the large payload — your API stays responsive.

---

## Installation

```bash
# Python 3.12+ (you will regret 3.11 when a wheel doesn't build)
uv venv --python 3.12
uv pip install \
  fastapi "uvicorn[standard]" \
  pydantic pydantic-ai \
  google-genai anthropic \
  dramatiq[redis] redis \
  av \
  yt-dlp \
  lancedb \
  langfuse \
  boto3 \
  tenacity \
  python-multipart

# Dev
uv pip install --dev pytest pytest-asyncio ruff mypy

# System deps
brew install ffmpeg redis                      # macOS
apt-get install -y ffmpeg redis-server         # linux
```

```bash
# Frontend
npm create svelte@latest web-ui
cd web-ui && npm install
npx shadcn-svelte init
npm install @tanstack/svelte-table video.js
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|---|---|---|
| Gemini 2.5 Flash (VLM) | Qwen2.5-VL self-hosted on Modal | Cost at scale exceeds budget, or IP/privacy requires on-prem. Not before you have gold-set accuracy numbers for comparison. |
| Gemini 2.5 Flash (VLM) | Gemini 2.5 Pro | Specific hard-clip reprocessing. Route based on a confidence score from Flash. |
| Claude Sonnet 4.5 (LLM) | Gemini 2.5 Pro | Want a single-vendor stack, accept slightly worse rule-following. |
| Claude Sonnet 4.5 (LLM) | Claude Opus 4.7 | Batch audit / gold-label generation / final-pass correction review. |
| Pydantic AI | Raw SDKs + tenacity | If Pydantic AI stalls or blocks you. Migration is trivial. |
| Pydantic AI | DSPy | Later, as a specialized optimizer over the few-shot bank. Not as primary orchestrator. |
| Dramatiq | Modal Functions | When the workload is GPU-bound and you want autoscale-to-zero. Hybrid: Dramatiq for CPU work, Modal for GPU. |
| Fly.io | Railway | If Fly's CLI ergonomics ever annoy you, Railway is a near-equivalent. |
| SvelteKit | Next.js 15 | If your team grows and your next hire is a React dev. |
| LanceDB | sqlite-vec | Even simpler — embed vectors right in SQLite. Fine for <10k examples. Switch if LanceDB's file management becomes annoying. |
| Cloudflare R2 | AWS S3 | If you already live in AWS-land and cross-service IAM matters more than egress cost. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|---|---|---|
| **LangChain** | Hides the prompt from you. Fatal for a project where "external memory = explicit prompts" is the thesis. Also: frequent breaking changes, too many abstractions for a solo dev to track. | Pydantic AI or raw SDKs. |
| **LangGraph** | Graph abstraction for a pipeline that isn't graph-shaped (we have 2 sequential stages, not branching multi-agent dialogue). Overhead without benefit. | Plain Python `async` + Pydantic AI. Revisit if we add genuinely multi-agent workflows. |
| **GPT-4o or Claude as the VLM** | No native video input; per-frame billing at 3fps × 60min = ~10k frames is order-of-magnitude more expensive than Gemini's native video. | Gemini 2.5 Flash for perception. Reserve GPT/Claude for text-shaped interpretation. |
| **FastAPI BackgroundTasks for video jobs** | Runs in API event loop; 10-minute job will starve request handlers and not survive a restart. | Dramatiq + Redis. |
| **decord** | Project activity slowed; broken wheels on Python 3.12+ intermittently. | PyAV 13+. |
| **Celery** | Overkill for a 2-queue solo-dev setup. Configuration surface is enormous; docs are Django-centric. | Dramatiq. |
| **Pinecone / Weaviate Cloud** | Vendor lock-in, monthly cost, cold-start latency on free tier, for <100k examples. | LanceDB (embedded). |
| **yt-dlp in production user-facing ingestion** | Violates YouTube ToS; legal risk; also fragile to YouTube changes. | Require users to upload their own footage, or partner with sources (UFA) for legitimate access. |
| **Astro for this frontend** | Static-first; we have an app-like UI (live job status, uploads, interactive corrections). | SvelteKit. |
| **HTMX-only for this frontend** | Video timeline scrubber + correction state doesn't map well to HTMX's form-centric model. | SvelteKit (or HTMX layered *inside* SvelteKit for forms if you really want). |
| **Training a custom VLM** | Explicitly out of scope per PROJECT.md. Frontier VLM + memory is the thesis. | Gemini 2.5 Flash + the memory store. |
| **Storing videos long-term** | Explicitly out of scope per PROJECT.md. Also, storage costs compound. | R2 with 7-day lifecycle rules. |

---

## Stack Patterns by Variant

**If the prototype shows Gemini 2.5 Flash can't reliably discriminate possession transitions:**
- Fall back to Gemini 2.5 Pro as the default VLM.
- Cost goes from ~$0.40 to ~$1.60/game — still well inside "per-game cost visible" discipline.
- Only after that fails, explore self-host Qwen2.5-VL for domain-specific fine-tuning.

**If per-game VLM cost becomes the dominant line item at alpha scale:**
- Aggressive sub-sampling: drop from 1fps to 0.5fps except around motion spikes (use PyAV scene-change detection as the "when to sample more densely" trigger).
- Batch multiple points into one Gemini call (you can send multiple video segments in one request).
- Cache the "rules + schema" prompt block — Gemini 2.5 has implicit caching for repeated prefixes.
- Only then consider self-host.

**If alpha coaches generate corrections faster than you expected:**
- Move the few-shot retrieval prompt into Claude prompt caching (1-hour TTL for hot examples).
- Add a nightly "consolidation" job where Opus 4.7 reviews corrections and proposes rule updates (human-approved before merging).

**If you want a single-vendor stack (for simplicity) instead of Gemini + Claude:**
- Gemini 2.5 Pro for both VLM and LLM. Slightly weaker rule-following than Claude, but you save one API contract and one observability integration. Acceptable tradeoff if simplicity > last-10% accuracy.

**If the project grows beyond solo and a team joins:**
- Migrate Dramatiq→Celery if you need more scheduling features.
- Migrate SvelteKit→Next.js if your hires are React-shaped.
- Adopt LangGraph if you add real multi-agent workflows (e.g., separate agents per event type).

---

## Version Compatibility

| Package | Compatible With | Notes |
|---|---|---|
| `pydantic-ai` | `pydantic>=2.9`, `python>=3.10` | Pin Pydantic AI version; pre-1.0 API churn is real. |
| `av` (PyAV) | `ffmpeg 6.x`, `python 3.10-3.13` | Confirm arm64 wheel on macOS before committing. |
| `dramatiq[redis]` | `redis-py>=5`, `python>=3.9` | `dramatiq-abort` is a useful companion for mid-job cancels. |
| `google-genai` | Python 3.10+, replaces old `google-generativeai` | Make sure you're on the *new* SDK (package name changed in 2025). |
| `anthropic` (Python SDK) | Python 3.9+ | `AsyncAnthropic` is the one you want for fan-out. |
| `lancedb` | Python 3.10+, arrow/lance | Storage path versioned; plan for schema migration. |

---

## Sources

### Official docs (HIGH confidence)
- [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) — verified 2026-04-20: Gemini 2.5 Flash $0.30/$2.50 text/image/video input/output, Pro $1.25/$10.00 (≤200k), prompt caching $0.03/$0.125 respectively.
- [Gemini API video understanding](https://ai.google.dev/gemini-api/docs/video-understanding) — verified: 1fps native sampling, ~300 tok/sec, File API for >20MB or >1min, up to 2hr on 2M-ctx variant.
- [Claude API pricing](https://platform.claude.com/docs/en/about-claude/pricing) — verified 2026-04-20: Sonnet 4.5 $3/$15 with 0.1x cache reads; Opus 4.7 $5/$25 (new tokenizer, uses up to 35% more tokens); batch 50% discount stacks with caching.
- [OpenAI API pricing](https://openai.com/api/pricing/) — verified: GPT-4o $2.50/$10, GPT-4.1 $2.00/$8, image tokens per tile ~255 (low) / ~1105 (high detail).
- [Modal pricing](https://modal.com/pricing) — verified: H100 $0.001097/sec, A100-80 $0.000694/sec, A10 $0.000306/sec, $30/mo free credit.
- [Cloudflare R2 pricing](https://www.cloudflare.com/products/r2/) — verified: $0.015/GB-mo storage, zero egress.

### Verified cross-references (MEDIUM-HIGH confidence)
- [Artificial Analysis — Gemini 2.5 Pro](https://artificialanalysis.ai/models/gemini-2-5-pro) — independent benchmarks.
- [Qwen2.5-VL HuggingFace](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct) — hour-plus video temporal grounding confirmed.
- [BentoML 2026 open-source VLM guide](https://www.bentoml.com/blog/multimodal-ai-a-guide-to-open-source-vision-language-models) — Qwen2.5-VL positioning vs Llama Vision / Pixtral / InternVL.
- [Langfuse vs alternatives](https://langfuse.com/faq/all/best-phoenix-arize-alternatives) — cost-tracking feature parity.
- [Dramatiq motivation docs](https://dramatiq.io/motivation.html) — explicit design-philosophy comparison vs Celery.
- [Vector DB 2026 comparison (4xxi)](https://4xxi.com/articles/vector-database-comparison/) — LanceDB vs Chroma vs Qdrant at solo-dev scale.
- [ZenML Pydantic AI vs LangGraph](https://www.zenml.io/blog/pydantic-ai-vs-langgraph) — lock-in comparison.
- [PydanticAI persistent memory via Hindsight](https://hindsight.vectorize.io/blog/2026/03/09/pydantic-ai-persistent-memory) — memory pattern for future consideration.
- [Fly.io vs Railway 2026](https://thesoftwarescout.com/fly-io-vs-railway-2026-which-developer-platform-should-you-deploy-on/) — solo-dev rating.
- [FastAPI vs Litestar 2026](https://byteiota.com/litestar-vs-fastapi-python-speed-test-2026-analysis/) — framework maturity.

### Lower-confidence signals (LOW, flagged)
- SvelteKit vs Next.js for dashboards: multiple 2026 framework comparison posts agree, but this is opinion-driven. The Next.js path is equally viable; switch depends on team preference.
- Modal "3x production multiplier" — found in one secondary source ([Morph LLM](https://www.morphllm.com/modal-pricing)); verify in Modal billing docs before any scale-up plan.
- yt-dlp legal status for dev use — grey area; the project-level mitigation (require user-uploaded footage or licensed access in production) is the real answer, not a legal opinion.

---

*Stack research for: Ultimate Frisbee video-analytics (VLM + LLM + memory)*
*Researched: 2026-04-20*
