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
