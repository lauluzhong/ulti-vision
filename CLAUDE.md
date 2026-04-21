## Project

Sports Video Analytics — Ultimate Frisbee

## Technology Stack

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
| Job queue

