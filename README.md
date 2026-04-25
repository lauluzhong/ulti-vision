# Sports Video Analytics — Ultimate Frisbee

Turn existing, inconsistent-quality Ultimate Frisbee footage into a reliable per-point event timeline — without requiring the coach to watch the game.

An automated pipeline that extracts structured, timestamped game events (possessions, goals, completions, turnovers, throws) from raw Ultimate Frisbee footage using a VLM + LLM + external memory architecture.

## Prerequisites

- **Python 3.12** (exact — pinned in `.python-version`)
- **ffmpeg** — `brew install ffmpeg` on macOS
- **Docker Desktop** (for the local Postgres 16 + pgvector database)
- **uv** (recommended) — `brew install uv` or see [uv install docs](https://docs.astral.sh/uv/getting-started/installation/)

## Quickstart

```bash
# 1. Start the local Postgres + pgvector database
docker compose up -d db

# 2. Install the project and dev dependencies
uv sync --all-extras
# (or, if uv is unavailable: python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]')

# 3. Configure secrets — copy the template and fill in real API keys
cp .env.example .env
# then edit .env

# 4. Verify the CLI is wired up
python -m sva.cli --help
```

## Project Layout

The project uses the PEP 517 `src/` layout. Top-level Python package is `sva`.

- `sva.ingest` — video download, VFR→CFR transcode, PyAV frame extraction
- `sva.perceive` — VLM adapters (Gemini 2.5 Flash primary) producing structured observations
- `sva.interpret` — LLM adapters (Claude Sonnet 4.5) turning observations into canonical events
- `sva.memory` — external memory store (rules, examples, corrections) — swappable backend
- `sva.api` — FastAPI surface + Typer CLI (`sva` entry point)
- `sva.observability` — Langfuse tracing, cost aggregation

## Configuration

All secrets load from `.env` via `pydantic-settings`. Missing required keys raise a `ValidationError` at import time — see `src/sva/config.py`. The required keys are documented in `.env.example`.

## Deployment Shape

The current production shape is:

- Vercel for the SvelteKit frontend in `apps/web`
- Render for the Python backend
- Render Postgres for the relational database with `pgvector`
- Render Key Value (Redis-compatible) for Dramatiq queue transport
- A Render persistent disk mounted at `/app/data` for uploaded clips and transcoded video files

This repo now includes:

- [render.yaml](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/render.yaml) — Render Blueprint for backend + Postgres + Key Value
- [Dockerfile](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/Dockerfile) — backend image with ffmpeg installed
- [scripts/start_backend.sh](/Users/lauluzhong/Documents/Sports%20Video%20Analytics/scripts/start_backend.sh) — starts migrations, Dramatiq, and Uvicorn in one service

Important current constraint:

- The backend stores uploads and transcoded video on local disk (`data/uploads`, `data/transcoded`), so the simplest deploy is a single backend service that runs both the API and worker against one persistent disk.
- This is deliberate for v1. Splitting API and worker into separate services cleanly will require shared object storage later.
