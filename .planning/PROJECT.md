# Sports Video Analytics — Ultimate Frisbee

## What This Is

An automated pipeline that converts raw Ultimate Frisbee game footage into structured, timestamped event data — effectively replacing the "intern who sits in front of a game and counts the passes." A VLM extracts candidate observations from video, an LLM interprets them into canonical game events (completions, turnovers, goals, possession changes, throw types, pass direction), and an external memory store accumulates examples, rules, and corrections so the system compounds over time. Primary users are coaches; players are a secondary user group for self-review.

## Core Value

**Turn existing, inconsistent-quality Ultimate Frisbee footage into a reliable per-point event timeline — without requiring the coach to watch the game.** If that one thing works, everything else (dashboards, integrations, new sports) becomes viable. If it doesn't, nothing else matters.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

(None yet — ship to validate)

### Active

<!-- Current scope. Building toward these. Hypotheses until shipped. -->

**Pipeline**
- [ ] Accept a video file or public video URL (UFA YouTube, tournament streams, etc.) as input
- [ ] Sample frames at a configurable rate (default 1 fps — aligned with Gemini 2.5 Flash native video sampling; 3 fps is the v1 ceiling for cost discipline) and feed windowed clips to a VLM
- [ ] VLM emits structured candidate observations (what's visible, who has the disc, state of play)
- [ ] LLM interprets candidate observations into canonical game events using rules + few-shot examples from external memory
- [ ] External memory stores rules, positive/negative examples, and corrections — decoupled from model choice so VLM/LLM can be swapped

**Events detected in v1**
- [ ] Possession (team-level: which team has the disc)
- [ ] Goals / point end (with scoring team)
- [ ] Completions (successful passes)
- [ ] Turnovers (drops, throwaways, Ds, stalls — classification may defer, but "turnover occurred" in v1)
- [ ] Pass count per point
- [ ] Pass direction relative to field (up-field / down-field / lateral) — acknowledged to require extra work because field-line visibility varies
- [ ] Throw types (forehand / backhand / hammer / blade) — best-effort classification

**Output / UX**
- [ ] API + minimal web UI: upload video (or paste URL), get structured events back
- [ ] All event data breaks down **by point** (critical — non-negotiable)
- [ ] In-app event list (line-by-line) with timestamps that link back to video moments
- [ ] Stats dashboard (per-point breakdown, completion rates, turnover counts)
- [ ] Downloadable CSV / Excel export (JSON is available but not critical)
- [ ] Correction interface sufficient for alpha coaches to flag/fix wrong events → corrections feed back into external memory

**Quality bar for alpha**
- [ ] Target ~85% event recall on the "MVP event set" (possession, goals, completions, turnovers) with some false positives acceptable
- [ ] Hybrid evaluation: small human-labeled gold set (for regression testing) + coach corrections (expand eval set over time)

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- **Player identification (faces / names) in v1** — pure facial/jersey recognition from varied-angle amateur Ultimate footage is error-prone; defer to v2. Event schema reserves `player_id: null`. Roster + jersey-OCR or per-team few-shot fine-tune will be explored in a later milestone.
- **Chips / GPS tracking** — kills the "extract from existing footage" thesis and requires hardware buy-in.
- **Advanced stats and custom metrics (xG-analogs, PPR-style ratings, etc.)** — v1 establishes the event timeline; aggregate/derived metrics come later.
- **Tournament management, team management, roster/scheduling tools** — that's what existing products (Penultimate, UltiAnalytics, Hive, etc.) do. Stay focused on extraction.
- **Training a custom VLM from scratch** — the thesis is that frontier VLMs + external memory + LLM interpretation generalize better than bespoke deterministic CV. Revisit only if the hypothesis fails.
- **Near-live / in-game processing** — v1 is post-game only. Near-live is an end-state possibility, not a v1 feature.
- **Sports other than Ultimate Frisbee** — Ultimate is the hard case; generalization comes after it works.
- **Video hosting / long-term storage** — process and return results; do not become a video platform.

## Context

**Problem context**
- Ultimate Frisbee is underserved relative to "bigger" sports: growing volume of game footage but very little structured data derived from it.
- Video quality and consistency vary widely — different camera angles, obstructions (sideline players), handheld wobble, sunlight, partial field visibility.
- This inconsistency is precisely why traditional deterministic CV (explicit disc/player detectors) is hard to scale here — and why the user hypothesizes that VLMs + LLMs will do better because they generalize across visual contexts.

**User context**
- Primary: coaches who already review footage but don't get structured data out of it; also coaches who've *stopped* filming because post-production is too much work but would restart if they knew automatic extraction was available.
- Secondary: players for self-review / development.
- User plan for validation: dogfood solo first, then move quickly to a closed alpha of **2–5 friendly coaches**. Outputs must be "not entirely incorrect" before friendly coaches see them.

**Prior art / positioning**
- Reference product for UX envelope: [penultimateapp.com](https://penultimateapp.com) — simple web app with manual event entry, dashboard, line-by-line event log.
- Existing tools (UltiAnalytics, Huckmap, Hive, Penultimate, etc.) mostly rely on manual human entry or sideline scorekeeping.
- Positioning: be the **first (video→events) extraction layer** that can optionally feed existing tools via CSV/JSON, **AND** support a direct B2C path where any user uploads video and gets analytics back.

**Build context**
- Solo build, AI-assisted heavily. User directs, AI writes most code under user review.
- Timeline: staged — fast feasibility prototype (weeks) to validate the VLM+LLM pipeline end-to-end, then a slower architecture-focused build (~2 months) to get the VLM+LLM+memory architecture right *before* alpha. Reasoning: once alpha opens, coach corrections should compound memory fast — so the memory architecture must be ready to absorb them at that moment.

**Technical posture**
- Modular by design: VLM, LLM, and external memory are swappable. Memory is persisted outside the models so improvements in underlying models translate into better outputs without re-architecting.
- Footage sources for development: public streams (UFA YouTube, tournament / club streams). Legality/rights will need to be handled before any public launch.
- Iterative learning loop is core: the system improves through corrections, not upfront training.

## Constraints

- **Tech stack**: Hybrid hosting posture — start with managed VLM APIs (Gemini / GPT-4o / Claude) for speed; add self-hosted OSS option (Qwen-VL, Llama-Vision on Modal/RunPod or equivalent) if/when cost or control demands it.
- **Cost**: VLM inference over an hour of footage is non-trivial even at 1fps. Default sampling rate is 1fps (Gemini 2.5 Flash native video); 3fps is the v1 ceiling, not the target. Cost-per-game visibility is required from day 1; aggressive sampling / clip windowing / caching / batching must be design-level concerns.
- **Accuracy floor**: ~85% recall on core MVP events (possession, goals, completions, turnovers) is the alpha-gate. Below that, we do not show coaches.
- **Data**: No own footage archive; dev and eval use public sources. A small human-labeled gold set is a prerequisite for measuring accuracy.
- **Team size**: Solo + AI-assisted. Architectural complexity must be tractable for one person to maintain.
- **Modularity**: Perception (VLM), interpretation (LLM), and memory must be independently replaceable. No design choice that couples all three.
- **Per-point decomposition is non-negotiable**: Every output must be sliceable by point.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| VLM + LLM + external memory over bespoke CV | Ultimate footage is too inconsistent for deterministic pipelines; VLMs generalize across visual contexts; external memory decouples knowledge from model choice. | — Pending |
| Defer player identification to v2 | Facial/jersey recognition from amateur, multi-angle Ultimate footage is error-prone; chips violate the "extract from existing footage" thesis. Keep `player_id: null` in v1 schema. | — Pending |
| v1 form factor = API + minimal web UI | Fastest shareable thing that lets 2–5 friendly coaches upload & get output; avoids full SaaS overhead. | — Pending |
| Staged timeline: prototype → architecture-first build → alpha | Alpha coaches' corrections should compound external memory; memory architecture must be ready *before* alpha opens. | — Pending |
| Hybrid hosting posture | Managed VLM APIs get us to prototype fast; self-host option stays on the table for cost/control if we scale. | — Pending |
| Human-correction structure in v1 | 85% recall + varied footage angles = corrections are inevitable. Write-path exists from day 1; polished review UI iterates from basic → better. | — Pending |
| Integrate-friendly CSV/Excel output (not just JSON) | Coach workflows run on spreadsheets; existing Ultimate tools consume CSV. JSON is engineering-facing, not user-facing. | — Pending |
| Ultimate Frisbee first, generalize later | Ultimate's inconsistent quality is the hard case — solving it yields a more robust system than starting with broadcast-quality sports. | — Pending |
| Frontier VLM APIs before custom training | Per the core thesis, improvements in underlying models should translate into better outputs without re-architecting. No custom model training in v1. | — Pending |
| WFDF rulebook as rule source | User preference over USAU. WFDF is the international standard; events are interpreted against WFDF rules at interpretation time. Rules are data (not code) so updates are a file change. | — Pending |
| Sampling rate: default 1 fps, ceiling 3 fps | Gemini 2.5 Flash native video sampling is 1 fps — matching the default keeps per-game cost in the ~$0.40 range. 3 fps is the v1 ceiling for cost discipline; exceeding it requires an explicit decision. | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-21 after WFDF rulebook + 1fps default amendments*
