# Feature Research

**Domain:** Video-to-events extraction pipeline — Ultimate Frisbee coaching analytics
**Researched:** 2026-04-20
**Confidence:** HIGH on event taxonomy and competitor gaps (verified against USAU rulebook, WFDF rules, UFA stats API glossary, Leaguevine key, Statto, UltiAnalytics); MEDIUM on integration surfaces (no public API spec found for any tool — all ingest appears CSV-only); LOW on field-aware vision claims (no authoritative benchmark for sideline-only Ultimate footage; camera angle research sourced from community guides and Stanford CV papers)

---

## Competitor Baseline (what existing tools do)

Understanding the competitive landscape is prerequisite to knowing what's table stakes vs. differentiator.

| Tool | Input Method | Event Types | Breakdown | Export | Video? | Status |
|------|-------------|-------------|-----------|--------|--------|--------|
| **Penultimate** | Manual, sideline, one-hand tap | Goals, assists, completions, turnovers, blocks | Per-point, per-player | Unknown (no public CSV spec found) | No | Active |
| **UltiAnalytics** | Manual, mobile, real-time | Passes, drops, assists, goals, Ds, throwaways | Per-player, per-game | CSV export via web | No | App removed from Play Store 2024; web may persist |
| **Statto** | Manual, pitch-tap with location | Passes, blocks, stall outs, goals, assists, Ds, throwaways with location data | Per-game, per-player, per-line (O/D), heatmap | CSV export | No (review via play-by-play) | Active; iOS only; $9.99 |
| **Hive Ultimate** | Manual / coach-submitted film analysis | Turnover-by-turnover coach-authored breakdown | Qualitative + strategic | None (Patreon content) | Human-reviewed film clips | Active; Patreon coaching service |
| **Huckmap** | Not found — may be defunct or internal | — | — | — | — | Unclear; no public product found |
| **UFA Stats API** | Professional league internal tracking | Goals, assists, blocks, O/D possessions, efficiency, break % | Per-player, per-line, per-game | API (docs.ufastats.com) | No | Pro league only |

**Key gap across all tools:** None do video-to-events extraction. Every tool requires a human sideline operator to key events in real time. The product being built is the first (video→events) layer.

**Integration posture:** No de-facto schema exists. Each tool rolls its own. CSV is the universal ingestion format by default, but field names differ. The product's CSV/Excel output should be designed to be easy to manually import into any of these tools, not natively compatible.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features a coach expects after seeing "upload your game footage and get analytics." Missing any of these causes immediate rejection.

| Feature | Why Expected | Complexity | Dependencies | Notes |
|---------|--------------|------------|--------------|-------|
| **Video ingest: file upload** | Core product premise | LOW | None | MP4/MOV. Max size TBD; use R2 signed upload. |
| **Video ingest: URL paste (YouTube/UFA streams)** | Coaches film and post to YouTube routinely; UFA streams are the reference content | LOW | None | yt-dlp for dev; production requires user to own the rights or provide signed URL. Add clear ToS copy. |
| **Async job processing with status indicator** | 60-min game takes minutes to process; coach must know it's running | LOW | Job queue (Dramatiq) | "Processing point 7 of 14" is better than a spinner. Stream per-point partial results. |
| **Per-point event timeline** | Non-negotiable per PROJECT.md. Every coach tool organizes by point | MEDIUM | Point detection | Point 1 → [pull, completion, completion, turnover, completion, goal]. Each row is an event. |
| **Timestamp deep-link (event → video)** | Coaches must be able to verify what the system detected; click event → jump to that video moment | MEDIUM | Video storage + video player | video.js or native `<video>` with `#t=` seek. Critical for trust-building with alpha coaches. |
| **Completion count and completion %** | The single most-used Ultimate stat; coaches expect it | LOW | Event pipeline | Count completions / (completions + turnovers). Broken out per point and game. |
| **Turnover count (total and per-point)** | Second most-used stat | LOW | Event pipeline | Total turnovers; turnovers per possession is a v1.x add-on. |
| **Goal / point outcome (which team scored)** | Minimum game-state output | LOW | Event pipeline | Required for O/D line context. |
| **Pass count per point** | Simplest useful stat; "we threw 18 times that point" tells a story | LOW | Event pipeline | Count of completions + turnovers per point. |
| **Stats dashboard (game-level summary)** | Coaches open the app to see numbers, not a raw event list | MEDIUM | Event store | Completion %, turnover count, goals, pass count, possessions. Single screen per game. |
| **CSV / Excel export** | Coaches live in spreadsheets; all existing Ultimate tools import CSV | LOW | Event store | Required for the "first extraction layer" positioning. Flat rows: game_id, point_id, event_type, timestamp, team, throw_type, pass_direction. |
| **Basic event correction: flag wrong event** | ~85% recall = ~15% errors; if coaches can't fix them, the product is unusable | MEDIUM | Correction store + memory writer | Minimum: "mark as wrong." Don't need full re-classification UI at v1 alpha, but need the flag. |
| **O-line vs. D-line point labeling** | Every serious Ultimate coach thinks in O-line / D-line frames. A "hold" vs. "break" structure is fundamental | MEDIUM | Point detection + possession tracking | Requires knowing which team is on offense at each pull. Derive from: team-that-scored-last = receives next pull (USAU rule). |
| **O-line conversion % and D-line break %** | The two canonical coaching metrics per UFA Glossary and Ultiworld analysis | LOW | O/D line labeling | Derived from hold/break counts. O-line conversion = holds / O-line possessions. D-line break = breaks / D-line possessions. |

### Differentiators (Competitive Advantage)

Features that make this product meaningfully better than manual keying. Prioritized by coach value × feasibility given the VLM-extraction architecture.

| Feature | Value Proposition | Complexity | Dependencies | Notes |
|---------|-------------------|------------|--------------|-------|
| **Automatic throw-type classification (backhand / forehand / hammer)** | No sideline keyer currently captures throw type automatically; Statto requires manual tap selection. Coaches use throw-type data to analyze team tendencies and individual player patterns | HIGH | VLM perception layer | VLM describes throwing motion and disc flight angle. Accuracy will be lower than for turnover/goal detection; provide confidence score. Common in-game throws: backhand, forehand (flick), hammer. Blade is rarer. |
| **Pass direction inference (upfield / lateral / downfield)** | Coaches care deeply about horizontal vs. vertical disc movement patterns; no existing tool captures this automatically | HIGH | Field-line detection heuristic OR VLM spatial reasoning | See "Field-Aware Features" section. Requires knowing which end of the field is which. High value but technically uncertain. Mark as MEDIUM confidence for v1; degrade gracefully to "unknown" when field orientation can't be inferred. |
| **Turnover sub-classification (throwaway / drop / block / stall / OOB)** | Coaches need "we had 4 throwaways and 2 drops" not just "6 turnovers." Existing tools track this but require manual real-time entry | MEDIUM | VLM + LLM interpretation | VLM can often distinguish: disc hits ground (drop), disc caught by defender (block/D), disc exits field boundary (OOB/throwaway), stall count event. Stall requires stall count visibility — unreliable. Default to "turnover" and classify where evidence supports it. |
| **Aggregated multi-game stats** | Single-game stats are noisy. Coaches want "across 5 games, our O-line conversion is X." No existing free tool does this automatically | MEDIUM | Multiple games processed; per-game stats schema | Build the schema to support this from day 1. Multi-game dashboard is a v1.x add once 2+ games are processed. |
| **Correction-fed memory improvement (the system gets better)** | Every other tool stays static. This product gets more accurate with each coach correction. Compounding accuracy is the unique moat | HIGH | Memory store + writer (full pipeline) | The core architectural differentiator. Coaches don't need to understand how it works; they just see accuracy improve over time. Surface in UI as "you've made 12 corrections; the system has learned from them." |
| **Throw-type mix per point / per possession** | Coaches want to know "this point was 80% backhand" or "this possession collapsed into hammer throws" — patterns invisible in manual box scores | LOW (once throw type is classified) | Throw-type classification | Simple aggregation over classified events. |
| **Point-by-point possession count (throws per possession)** | Efficiency metric: a 3-throw possession that scores is different from a 20-throw possession that scores | LOW | Per-point event timeline | Derive: count completions between each turnover/goal. |
| **Momentum detection (consecutive break points, scoring runs)** | "We went on a 4-0 run in the second half" — coaches know this intuitively but can't quickly pull it from manual data | LOW (derived) | Per-point event timeline with team score | Derived from score progression. Flag 2+ consecutive scores by one team, or 2+ consecutive D-line breaks. |
| **Automatic highlight clip generation (goals, layout grabs, blocks)** | Coaches spend hours cutting clips for player development. Auto-generated clips from event timestamps save hours | HIGH | Event timestamps + video storage + clip extraction | Feasible: events have timestamps; clips are ffmpeg extracts. The hard part is the subjective "is this highlight-worthy" judgment. Safer framing: "here are all goals with 10s context clips." Simple version is viable in v1.x. Research found a Stanford 2025 paper doing exactly this with MLLMs. |

### Anti-Features (Do Not Build)

These sound reasonable but are deliberately excluded. The exclusion reasons feed into why the product stays focused.

| Feature | Why Requested | Why NOT Building It | What to Do Instead |
|---------|---------------|--------------------|--------------------|
| **Player face / jersey identification (v1)** | Coaches want per-player stats | Amateur footage angles are too varied; jersey OCR fails without close-up frames; facial recognition from sideline footage is unreliable. Building it badly poisons trust. Per PROJECT.md explicit deferral. | Reserve `player_id: null` in v1 schema. Add per-player tracking in v2 after video quality expectations are established. |
| **Tournament management** | Complete team management feels natural to add | Different product. Existing tools (Penultimate, UltiAnalytics, Hive, Leaguevine, Ultimate Central) do this. Competing with them splits focus from the extraction thesis. | CSV export feeds those tools. Stay in the extraction lane. |
| **Roster / scheduling tools** | Coaches manage rosters elsewhere | Same as tournament management — wrong product shape. | Out of scope per PROJECT.md. |
| **Native video hosting / long-term storage** | "Keep all my game videos here" | Becomes a storage-cost liability; licensing risk with third-party footage; not the core value. R2 with 7-day lifecycle already decided. | Process → return results → delete video. Tell coaches to keep their own master copies. |
| **AI coaching recommendations ("you should run more vertical stack")** | Sounds like value-add | Coaches will not trust automated prescriptive advice from a system that can't watch their team practice. It also creates liability ("I followed the app's advice and lost"). | Show coaches what happened (descriptive). Let them draw their own conclusions. Add "insights" (e.g., "turnover rate was 40% higher in points 10+") that surface patterns without prescribing solutions. |
| **Machine-generated scouting reports without coach input** | "Generate a report on the opponent" | Requires opponent footage the system hasn't processed; generated prose about a team the system barely knows invites hallucination and erodes trust. | Offer exportable data summaries; let coaches write their own scouting reports using the raw stats as inputs. |
| **Near-live / in-game processing** | Sideline use during games | Processing latency is minutes-to-tens-of-minutes for v1; architecture is post-game only per PROJECT.md. Near-live requires a fundamentally different sampling and streaming architecture. | Post-game analysis only. State this clearly in product copy so coaches don't expect sideline use. |
| **Chips / GPS tracking integration** | "More precise location data" | Requires hardware buy-in from teams; kills the "extract from existing footage" thesis. | Stick to video. Field-position inference from video is imprecise but free. |
| **Custom VLM training** | "Fine-tune on Ultimate footage for better accuracy" | Out of scope per PROJECT.md thesis: frontier VLMs + memory compound better than bespoke models. Also: training data collection, labeling, compute, and model ops are enormous scope increases. | External memory + corrections is the compound mechanism. Revisit custom training only if the frontier VLM thesis fails. |
| **Stall count detection** | Coaches want stall violations tracked | Stall count is called verbally by the marker; not typically visible on video. Camera audio may not be reliable enough to detect "ten" consistently across footage types. | Flag "stall out" turnover only when a specific visual / audio signal is observed. Default to "turnover: unknown subtype." Revisit with better audio processing in v2. |
| **Foul / travel / pick event detection** | Complete rulebook coverage | Fouls, travels, and picks are contested calls; they produce stoppage but typically don't result in a clean visual event — the disc stays in one spot, players discuss, then play resumes. VLM cannot reliably distinguish a contested foul stop from a brief timeout. False positives on these events are high and low value. | Track "play stoppage" events as a generic signal. Let coaches manually annotate foul/travel/pick events via the correction interface if they want that detail. |

---

## Ultimate-Specific Event Taxonomy

### Canonical v1 Event Set (USAU Rulebook-Aligned)

The USAU 2024-2025 rulebook and WFDF rules define turnovers in two categories: those without play stoppage and those with stoppage. The UltiAnalytics and UFA stat systems use a simplified but real-world-tested taxonomy. The v1 event schema should align with the simplified taxonomy — comprehensive enough to satisfy coaches, simple enough for the VLM to detect reliably.

**Recommended v1 closed `event_type` enum:**

| Event Type | USAU Rule Basis | VLM Detectability | v1? | Notes |
|------------|-----------------|-------------------|-----|-------|
| `pull` | Start of each point; pulling team kicks to receiving team | MEDIUM | YES | Visual: disc thrown from goal line toward opposite end. Helps anchor point start detection. |
| `possession_start` | Derived: which team has the disc | HIGH | YES | Team-level; `player_id: null` in v1. |
| `completion` | Pass caught by offensive player; disc retained by offense | HIGH | YES | Most common event; bread and butter of the pipeline. |
| `turnover` | Catch fails, disc to ground, disc OOB, defender catches = defense gains possession (USAU 8.4, 13) | HIGH | YES | Sub-types below are best-effort. |
| `turnover:throwaway` | Thrower releases disc that lands OOB or is not caught | HIGH | YES (most cases) | Disc visibly leaves field or hits ground without defensive contact. |
| `turnover:drop` | Receiver fails to hold on to catchable disc | MEDIUM | YES (most cases) | Disc contacts ground after receiver contact. |
| `turnover:block` | Defender contacts disc mid-air, causing incompletion (USAU uses "D") | HIGH | YES | Defender arm/hand visibly contacts disc. |
| `turnover:stall_out` | Thrower does not release before "ten" in stall count | LOW | DEFER | Requires audio or stall count visibility. Emit as `turnover` with `subtype: unknown` unless evidence is clear. |
| `turnover:out_of_bounds` | Disc exits field boundary | HIGH | YES | Disc visibly crosses sideline or back line. |
| `goal` | Disc caught in opponent's end zone by offensive player (USAU 8.3) | HIGH | YES | Clear visual: player in end zone catches disc; celebration follows. |
| `point_end` | Derived from `goal`; point number increments | HIGH | YES | Composite of `goal` event + score update. |
| `brick_called` | Receiving team invokes brick option after pull OOB (USAU 8.E) | LOW | DEFER | Visual: player raises hand overhead. Rare enough to omit in v1. |
| `unknown` | System could not classify the observed action | — | YES | Safety valve; emit with low confidence. Coach sees "unclassified event at 14:32" and can flag/correct. |

**Events to defer to v2+ (not in v1 enum):**

| Event Type | Why Deferred |
|------------|-------------|
| `foul` | Contested; no clean visual signal; high false positive risk |
| `travel` | Observer call; disc stays in place; indistinguishable from normal stoppage |
| `pick` | Defensive call during player movement; no disc-visible signal |
| `stall_out` (classified) | Requires reliable audio or on-screen stall counter |
| `timeout` | Generic stoppage; not a game-state event coaches analyze |
| `injury_stoppage` | Rare; not analytically meaningful |

### Rulebook Variations by Competition Level

Different competition levels follow slightly different frameworks. The event taxonomy above applies to USAU club and college play. Key variations:

| Level | Rules Body | Key Differences Affecting Event Tracking |
|-------|-----------|------------------------------------------|
| **USAU Club / College** | USAU 2024-2025 (or 2026-2027 per latest update) | Self-officiated. No observers in most club play. Spirit of the Game drives contested calls. Standard stall count to 10. |
| **UFA Pro** | UFA / USAU-derived with observer rules | Observers make active calls. UFA Stats API provides professional-grade event data. Pull data is highly consistent. |
| **WFDF (international)** | WFDF 2021+ | Minor differences in turnover definitions (see WFDF comparison document). Stall count language differs slightly. `Handover` and `deflection` turnovers are explicitly named (WFDF 13.2) — not commonly tracked in club play. |
| **Youth** | USAU youth guidelines with adaptations | Shorter stall count (sometimes 8); shorter game to cap; "spirit circle" mandatory. Point length is shorter on average — affects pass-per-possession norms. |
| **Recreational / pickup** | Varies by community | Often use simplified USAU rules. Brick calls uncommon. Stall count may be shorter. |

**Practical impact for v1:** Build against USAU 2024-2025 club/college rules. This covers the widest alpha coach audience. UFA Pro data is not needed for alpha. Note in-app that the system uses USAU club-level event definitions.

---

## Integration Surfaces

**Finding:** No de-facto standard Ultimate Frisbee event data schema exists. Every tool uses its own internal representation. There is no public API spec for Penultimate, Statto, or UltiAnalytics. The only public-facing API is the UFA Pro Stats API (`docs.ufastats.com`), which covers professional data only.

**What currently exists:**

| Tool | Ingest Format | Field Names Known | Confidence |
|------|--------------|-------------------|------------|
| UltiAnalytics | CSV (proprietary) | goals, assists, blocks (>20 columns per dfiorino/ultianalyticspull) | MEDIUM — inferred from ultianalyticspull column descriptions |
| Statto | CSV export | Raw stats; location-enhanced | MEDIUM — app store descriptions confirm CSV export |
| Penultimate | Unknown | Unknown | LOW — no public CSV spec found |
| UFA Stats API | REST/JSON | O-line conversion, break %, possessions, efficiency per UFA Glossary | HIGH — public docs exist |
| Leaguevine | Unknown | goals, assists, completions, Ds, throwaways, plus/minus | MEDIUM — stats key page describes fields |

**Recommendation for export design:**

Design one authoritative flat CSV format that any coach can import into Excel or Google Sheets without transformation. Each row is one event. Columns:

```
game_id, game_date, point_number, point_type (O/D), possession_number,
event_sequence, event_type, event_subtype, team, player_id,
video_timestamp_ms, throw_type, pass_direction, confidence,
corrected (bool), notes
```

This schema is more detailed than any existing tool's import format. To feed specific tools, coaches will need to use Excel formulas or a simple import script — there is no "native import" button in any tool. Do not over-engineer cross-tool compatibility in v1; the extraction value is sufficient on its own.

**JSON API:** Offer a JSON endpoint alongside CSV. Required by any developer who builds on top of this product. Not user-facing but necessary for the "first extraction layer" positioning.

---

## B2C First-Upload Experience (Value in 5 Minutes)

For a coach or player who uploads their first game without any setup:

**Must deliver in the first 5 minutes:**
1. A per-point event list that looks plausible — even if not perfect. "Here are the 15 points of your game with events" is immediately legible to any Ultimate player. The key is it must look like it understands Ultimate, not like a generic sports detector.
2. A single-number stat that surprises or confirms: "Your O-line converted 7 of 9 possessions (78%)." Coaches either knew this intuitively and feel validated, or didn't track it and feel immediately informed.
3. One timestamp deep-link that works. Clicking on an event and landing at the right video moment in under 2 seconds is the single biggest trust-builder in v1.
4. The event list must be organized by point, not by time. This is how Ultimate players think. A flat time-sorted list signals the product doesn't understand the sport.

**What to avoid in the first-upload experience:**
- Do not surface confidence scores prominently on first view. "This completion has 63% confidence" is confusing before the coach understands the system's accuracy range.
- Do not block on video processing before showing partial results. Stream point-by-point as events are ready. "Points 1–4 complete, processing point 5..." is better than a blank loading screen.
- Do not ask for roster information during onboarding. The product works without it in v1.

---

## Correction-Loop Features

### Essential Corrections to Support (Feed Memory Usefully)

| Correction Type | Why Useful | Memory Benefit | Complexity |
|-----------------|------------|----------------|------------|
| **Flag event as wrong** | Simplest correction; coach marks an event "incorrect" without specifying what it should be | Provides negative training signal: "observations of this shape DID NOT produce this event type" | LOW |
| **Re-classify event type** | Coach changes `turnover` to `completion` or vice versa | Provides both negative (original) and positive (corrected) training signal — the highest-value correction | MEDIUM |
| **Re-classify turnover sub-type** | Coach changes `turnover:unknown` to `turnover:drop` | Refines the taxonomy; helps the system learn sub-type visual signatures over time | MEDIUM |
| **Re-classify throw type** | Coach changes `backhand` to `forehand` | Helps calibrate throw-type classification accuracy; especially useful early when VLM throw-type accuracy is lower | LOW |
| **Mark missed event** | Coach identifies that an event was missed entirely (false negative) | Provides a positive training signal where the system previously produced no output; requires the coach to specify the event type and click to the correct timestamp | HIGH |
| **Correct possession assignment** | Coach changes which team is assigned an event | Fixes team-possession tracking errors that cascade into O/D line stats | MEDIUM |
| **Correct point boundary** | Coach moves the start/end timestamp of a point | Fixes point detection errors that cause all events to be misattributed to the wrong point | HIGH |

### Corrections NOT to Support (Do Not Feed Memory Usefully)

| Correction Type | Why Not |
|-----------------|---------|
| **Edit free-form notes** | Notes are non-structured; they don't produce typed examples for memory retrieval. Give coaches a notes field per event for personal annotation, but don't route it into the memory loop. |
| **Delete spurious events** | "Delete" is a flag-as-wrong correction in disguise. Implement as "mark incorrect" not a hard delete. Rationale: immutable event table, corrections as separate records (per ARCHITECTURE.md anti-pattern note). |
| **Bulk corrections ("all turnovers in this game are wrong")** | Too coarse to produce useful per-example memory records. Would need to be decomposed into individual corrections to be useful. |
| **Re-order events within a point** | Sequence reordering doesn't correspond to a memory-learnable visual pattern; it corrects a timing bug not a classification error. |
| **Correct player identification in v1** | `player_id: null` in v1 schema. No player identity to correct. |

**Scope discipline:** default all new corrections to `coach:<id>` scope. Promote to `global` only after multi-coach corroboration (per ARCHITECTURE.md). This prevents one coach's unusual scoring conventions from poisoning other coaches' results.

---

## Field-Aware Features

### Visual Cues That Are Reliable

| Visual Cue | Reliability from Sideline Video | Reliability from Endzone Video | Notes |
|------------|--------------------------------|-------------------------------|-------|
| **8 corner cones** | MEDIUM — visible when camera angle is good; soft cones can blow over; color varies | HIGH — endzone corner cones are prominent | The most reliable absolute field-position markers. Bright orange/red typically. |
| **End zone lines (goal lines)** | MEDIUM — visible as painted/chalked lines when field is dry; washed out in rain or high grass | HIGH — clearly visible from endzone angle | Can anchor "this throw landed in the end zone" vs. not. |
| **Sidelines** | LOW-MEDIUM — partially obscured by sideline players, bags, tents | MEDIUM — sideline visible from above | Often blocked by crowd. |
| **Brick mark (circle + cross at 20yd from goal line)** | LOW — small, often painted in grass, rarely visible on video | LOW | Do not rely on this for field orientation. |
| **Midfield mark** | LOW — similar to brick mark | LOW | Do not rely on this. |
| **End zone back line** | MEDIUM — like goal line | HIGH | |
| **Team color/uniform contrast** | HIGH — if teams wear clearly contrasting colors, "dark team" vs. "light team" is reliable | HIGH | Most competitive games have contrasting kits. Rely on this. |
| **Score overlay / scoreboard** | HIGH when visible — many UFA/tournament streams have on-screen overlays | HIGH when visible | Text-visible scoreboards are the best anchor for game state. Use OCR aggressively. |
| **Disc color (white, yellow)** | MEDIUM — disc is small and fast; blur is common | MEDIUM | Disc visibility is the hardest detection problem in the literature. |

### Field Orientation (Required for Pass Direction)

Inferring "upfield" vs. "downfield" requires knowing which end of the field each team is attacking. Reliable signals:

1. **Score overlay direction inference**: If team A just scored in the right end zone (visible from scoreboard + celebration cluster location), team A attacks left on the next point. This is the most reliable heuristic.
2. **Pull direction**: At the start of each point, the pulling team throws toward their own end zone. If pull direction and field cones are visible, field orientation can be locked for that point.
3. **Goal event anchor**: The VLM can ask "where in the frame did the disc land when the goal was scored?" End zone = far end of the frame. Reset per point.

**Practical recommendation:** Attempt pass direction inference when field orientation is determinable (score overlay visible, or pull direction visible). Default to `pass_direction: "unknown"` when it is not. Do NOT emit false direction labels. A VLM confidence threshold for direction should be applied: if the model is not confident, emit `unknown`.

### What Is Typically Invisible or Inconsistent in Amateur Footage

- Brick mark: almost never visible on standard sideline game footage
- Stall count: not visible, audio unreliable
- Exact player positions (coordinates): requires overhead drone or computer vision bounding boxes — not available from standard sideline footage
- Jersey numbers: too small and too motion-blurred at typical filming distances
- Force direction set by the defense: not visually detectable from single-camera footage

---

## Dashboards and Stats

### Canonical Per-Game Stats (v1 Priority)

| Stat | Definition | Source Events | v1? |
|------|-----------|---------------|-----|
| **O-line conversion %** | Holds / O-line possessions × 100 (UFA Glossary definition) | goals, turnovers, possession tracking | YES |
| **D-line break %** | Breaks / D-line possessions × 100 (UFA Glossary definition) | goals, turnovers on D possessions | YES |
| **Overall completion %** | Completions / (completions + turnovers) × 100 | completion, turnover events | YES |
| **Total turnovers** | Count of all turnover events | turnover events | YES |
| **Turnover type distribution** | Throwaway / drop / block / stall / OOB as % of total turnovers | turnover sub-type classification | YES (best-effort classification) |
| **Goals scored by team** | Count of goal events per team | goal events | YES |
| **Points played (total, O-line points, D-line points)** | Count per type | point_type per point | YES |
| **Average passes per possession** | Completions per possession (between turnovers) | completion, turnover, possession_start events | YES |
| **Throw type mix (% backhand / forehand / hammer)** | Distribution of classified throw types | completion + throw_type field | YES (best-effort) |
| **Pass direction distribution (% upfield / lateral / downfield)** | Distribution of classified pass directions | completion + pass_direction field | YES where determinable |

### Canonical Per-Point Stats (v1 Priority)

| Stat | Definition | v1? |
|------|-----------|-----|
| **Point outcome** | Hold / break / unknown | YES |
| **Pass count** | Total completions in the point | YES |
| **Turnovers in point** | Count of turnover events | YES |
| **Possessions per point** | Number of possession changes + 1 | YES |
| **Scoring team** | Which team scored the point | YES |

### v2+ Stats (Deferred — Require Player ID or Multi-Game Data)

| Stat | Why Deferred |
|------|-------------|
| **Per-player completion %** | Requires `player_id` — deferred to v2 |
| **Per-player assist count** | Requires `player_id` |
| **Per-player turnover count** | Requires `player_id` |
| **Plus/minus per player** | Requires `player_id` |
| **Cross-game O/D conversion trends** | Requires multiple games processed; schema ready from v1, UI deferred |
| **Scoring run / momentum by quarter** | UFA segments games into quarters; club games do not. Multi-game momentum analysis requires consistent point tagging first. |
| **Expected goals (xG) or Field Value** | Requires field position data (coordinates), which is not available from single-camera amateur footage. Research-grade metric (MIT Sloan 2025 paper uses UFA data with location tracking). |

---

## Feature Dependencies

```
[Video Ingest: file upload / URL]
    └──required by──> [Async job processing]
                          └──required by──> [Per-point event timeline]
                                                 └──required by──> [Stats dashboard]
                                                 └──required by──> [O/D line labeling]
                                                                       └──required by──> [O-line conversion % / D-line break %]
                                                 └──required by──> [CSV / Excel export]
                                                 └──required by──> [Timestamp deep-link]

[Per-point event timeline]
    └──required by──> [Completion count / %]
    └──required by──> [Turnover count]
    └──required by──> [Pass count per point]
    └──required by──> [Throw-type classification]
    └──required by──> [Pass direction inference]

[Point detection]
    └──required by──> [Per-point event timeline]
    └──required by──> [O/D line labeling]

[O/D line labeling]
    └──required by──> [O-line conversion % / D-line break %]
    └──required by──> [Multi-game O/D trend stats (v2)]

[Event correction: flag wrong event]
    └──required by──> [Event correction: re-classify event type]
    └──required by──> [Correction → memory loop]
                           └──required by──> [Accuracy improvement over time]

[Field orientation inference]
    └──required by──> [Pass direction inference (reliable)]

[Video timestamp]
    └──required by──> [Timestamp deep-link]
    └──required by──> [Highlight clip generation (v1.x)]

[Throw-type classification]
    └──enhances──> [Throw-type mix dashboard stat]

[Pass direction inference]
    └──enhances──> [Pass direction distribution stat]

[Turnover sub-type classification]
    └──enhances──> [Turnover type distribution stat]

[Multi-game processing]
    └──required by──> [Aggregated multi-game stats (v1.x)]
    └──required by──> [Cross-game trend dashboards (v2)]
```

### Key Dependency Notes

- **Point detection is the most critical dependency:** If point detection is wrong, every event is misattributed to the wrong point. Build it early, make it editable by coaches, and treat the editable point boundary as a first-class correction type.
- **O/D line labeling depends on knowing which team is pulling.** This is derived from "team that scored last = receives next pull." Requires reliable goal detection. A chicken-and-egg risk: if goal detection fails, O/D line labeling cascades incorrectly.
- **Pass direction inference depends on field orientation, not just VLM spatial reasoning.** The direction of "upfield" cannot be inferred without knowing which end zone each team is attacking. Always degrade gracefully to `unknown` rather than guessing.
- **Throw-type classification can degrade gracefully.** `throw_type: null` is acceptable; the event is still useful without it. Do not block other features on throw-type quality.

---

## MVP Definition

### Launch With (v1 Alpha to 2–5 Coaches)

Minimum viable product to validate the extraction thesis and get meaningful corrections from friendly coaches.

- [ ] Video ingest (file upload + YouTube URL)
- [ ] Async processing with per-point progress indicator
- [ ] Per-point event timeline (completion, turnover, goal, possession_start, point_end)
- [ ] Timestamp deep-link: click event → seek video to that moment
- [ ] Stats dashboard: completion %, turnover count, O-line conversion %, D-line break %, pass count per point
- [ ] O/D line labeling per point (hold / break / unknown)
- [ ] Turnover sub-classification as best-effort (throwaway, drop, block, OOB; emit `unknown` when uncertain)
- [ ] Throw type as best-effort (backhand, forehand, hammer; emit `null` when uncertain)
- [ ] Pass direction as best-effort with graceful `unknown` fallback
- [ ] Event correction: flag as wrong + re-classify event type
- [ ] Correction → memory feedback loop
- [ ] CSV export (flat event rows)
- [ ] ~85% recall on completion/turnover/goal detection (alpha gate)

### Add After First Correction Cycle (v1.x)

After alpha coaches have made enough corrections to validate the memory loop:

- [ ] Multi-game aggregated stats dashboard (requires 2+ games processed per coach)
- [ ] Highlight clip download: auto-generate clips for all goals, all blocks (ffmpeg extracts ± 10s around event timestamp)
- [ ] Turnover sub-type accuracy improvement (from corrections)
- [ ] Point boundary editor in UI (full correction flow, not just "flag")

### Future Consideration (v2+)

Features to defer until per-player tracking is feasible or multi-game data volume is sufficient.

- [ ] Player identification (jersey OCR, few-shot fine-tune per team) — unblock per-player stats
- [ ] Per-player stats: completion %, turnovers, assists, +/-
- [ ] Cross-game trend analysis (requires player continuity)
- [ ] Expected goals / field value model (requires location data)
- [ ] Near-live processing (requires architecture change)
- [ ] Opponent scouting from opponent-team footage

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Video ingest (file + URL) | HIGH | LOW | P1 |
| Async job + progress | HIGH | LOW | P1 |
| Per-point event timeline | HIGH | HIGH | P1 |
| Timestamp deep-link | HIGH | MEDIUM | P1 |
| Completion % | HIGH | LOW | P1 |
| Turnover count | HIGH | LOW | P1 |
| O/D line labeling | HIGH | MEDIUM | P1 |
| O-line conversion % / D-line break % | HIGH | LOW | P1 |
| CSV export | HIGH | LOW | P1 |
| Event correction (flag + re-classify) | HIGH | MEDIUM | P1 |
| Correction → memory loop | HIGH | HIGH | P1 |
| Stats dashboard | HIGH | MEDIUM | P1 |
| Throw-type classification (best-effort) | MEDIUM | HIGH | P1 (but degradable) |
| Turnover sub-classification (best-effort) | MEDIUM | MEDIUM | P1 (but degradable) |
| Pass direction (best-effort, `unknown` fallback) | MEDIUM | HIGH | P1 (but degradable) |
| Multi-game aggregated stats | HIGH | LOW (schema ready) | P2 |
| Highlight clip generation | MEDIUM | MEDIUM | P2 |
| Point boundary editor (full UI) | HIGH | MEDIUM | P2 |
| Momentum detection (scoring runs) | MEDIUM | LOW | P2 |
| Player identification | HIGH | HIGH | P3 |
| Per-player stats | HIGH | HIGH (depends P3) | P3 |
| xG / field value model | LOW (professional context) | VERY HIGH | P3 |
| Near-live processing | MEDIUM | VERY HIGH | P3 |

**Priority key:**
- P1: Must have for alpha launch
- P2: Add after first correction cycle / validation
- P3: v2+, after player ID is unblocked or scale warrants it

---

## Competitor Feature Analysis

| Feature | Penultimate | Statto | UltiAnalytics | This Product |
|---------|-------------|--------|---------------|--------------|
| **Video input** | No | No | No | YES — core differentiator |
| **Automatic event detection** | No (manual) | No (manual) | No (manual) | YES — core differentiator |
| **Per-point breakdown** | YES | YES | YES | YES — match or exceed |
| **O/D line stats** | YES (basic) | YES (with pitch tap) | YES (basic) | YES |
| **Throw-type tracking** | No | Manual selection on tap | No | YES (automatic, best-effort) |
| **Pass direction** | No | YES (pitch map tap) | No | YES (inferred, with fallback) |
| **Location heatmap** | No | YES (pitch-based) | No | No (no coordinate data from single-camera video) |
| **Timestamp deep-link** | No | No (play-by-play only) | No | YES — differentiator |
| **CSV export** | Unknown | YES | YES | YES |
| **Correction → improvement loop** | No | No | No | YES — differentiator |
| **Multi-game aggregation** | Unknown | YES | YES (web) | v1.x |
| **Highlight clips** | No | No | No | v1.x |
| **Player identification** | YES (manual entry) | YES (manual entry) | YES (manual entry) | v2+ |
| **Mobile sideline use** | YES | YES | YES | No (post-game only) |

**The fundamental gap this product fills:** Every competitor requires a human operator at the sideline entering data in real time. This product requires nobody at the sideline — the coach uploads existing footage and gets structured data back. This is the reason coaches who stopped filming will restart, and the reason coaches who currently use manual tools will consider this complementary rather than competing.

---

## Sources

- **USAU 2024-2025 Official Rules of Ultimate** — event and turnover definitions (usaultimate.org/wp-content/uploads/2023/12/Official-Rules-of-Ultimate-2024-2025.pdf)
- **WFDF Rules of Ultimate 2017 + USAU comparison** — WFDF-specific turnover taxonomy (wfdf.sport/wp-content/uploads/2020/07/wfdf_rules_of_ultimate_2017_-_usau_comparison.pdf)
- **WFDF Ch.13 Turnovers** — "down," "interception," "out-of-bounds," "stall-out," "handover," "deflection" definitions (urules.org/ch13.html) — HIGH confidence
- **UFA Stats Glossary** — O-line conversion %, D-line break %, hold %, offensive/defensive efficiency (watchufa.com/stats/glossary) — HIGH confidence (official professional league definitions)
- **Leaguevine Ultimate Stats Key** — 22 tracked metrics, event taxonomy (leaguevine.com/stats/stats/ultimate/key/) — HIGH confidence
- **UltiAnalytics** — mobile + web manual stat tracker (ultianalytics.com/details.html) — HIGH confidence
- **Statto app** — pitch-tap manual tracker with CSV export (statto.app/) — HIGH confidence
- **Hive Ultimate** — coach-curated film analysis service, not a software product (hiveultimate.com) — HIGH confidence re: positioning
- **dfiorino/ultianalyticspull README** — UltiAnalytics column structure (20+ stats); confirms goals, assists, blocks, year/game/quarter/point/possession columns — MEDIUM confidence (README, not full schema)
- **AUDL/UFA data science projects survey** (someflow.substack.com) — UFA Stats API at docs.ufastats.com; Python wrappers; MIT Sloan paper on completion probability and field value — MEDIUM confidence
- **FiveThirtyEight: Ultimate Frisbee in the Dark Ages of Analytics** — coach desires: hockey assists, pull statistics, WAR, heat maps; fundamental obstacle is manual collection burden — MEDIUM confidence (article undated but core thesis is consistent with 2026 reality)
- **Ultiworld Basic Team Analysis: Four Metrics** (2016) — O-line conversion, D-line break, as foundational coaching metrics — MEDIUM confidence (older article but metrics are stable)
- **Stanford 2025 MLLM Highlight Reel paper** — validates automatic highlight generation feasibility for Ultimate Frisbee using MLLM-based detection — MEDIUM confidence
- **Ultimate Frisbee filming guide research** — sideline occlusion, elevated camera advantage, cone visibility challenges (Quora, Ultiworld filming tips) — LOW-MEDIUM confidence (community guides, not systematic research)
- **PROJECT.md** — explicit scope boundaries (player ID, chips, tournament management, VLM training, near-live) — HIGH confidence (author-stated)
- **ARCHITECTURE.md** — event schema (`Observation`, `Event`, `MemoryRecord`), correction-as-first-class-data pattern, anti-pattern notes — HIGH confidence (derived from PROJECT.md constraints)

---
*Feature research for: Ultimate Frisbee video-analytics (VLM + LLM + memory pipeline)*
*Researched: 2026-04-20*
