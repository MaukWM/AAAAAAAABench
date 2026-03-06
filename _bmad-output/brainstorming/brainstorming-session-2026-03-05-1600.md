---
stepsCompleted: [1, 2, 3, 4]
session_active: false
workflow_completed: true
session_continued: true
continuation_date: 2026-03-06
inputDocuments: []
session_topic: 'Adapting BullshitBench viewer for AAAAAAAABench result display'
session_goals: 'Minimal, actionable viewer changes to display stuck/borderline/not_stuck results per model and per attack surface. Rank by vulnerability (most stuck = #1). Continuous scoring via avg tokens + stddev. Surgical changes to BB viewer only.'
selected_approach: 'ai-recommended'
techniques_used: ['morphological_analysis', 'scamper_method', 'reverse_brainstorming']
ideas_generated: [8]
context_file: ''
---

# Brainstorming Session Results

**Facilitator:** Mauk
**Date:** 2026-03-05

## Session Overview

**Topic:** Adapting BullshitBench's single-file HTML/JS viewer for AAAAAAAABench data presentation
**Goals:** Actionable, minimal changes to support: overall % performance (stuck/borderline/not_stuck per model), per-surface-area breakdowns, and any novel views unique to loop vulnerability benchmarking

### Context

**Source viewer:** BullshitBench `viewer/index.v2.html` (~3200 lines, vanilla JS, hand-coded SVG, no dependencies)
**BB visualizations:** Stacked bars (green/amber/red), domain heatmap, scatter plots (time/reasoning), technique breakdown, leaderboard, response drilldown
**Our data:** `responses.jsonl` with per-response: model, category, surfaces[], detection (classification/stuck/borderline/not_stuck), completion_tokens, max_tokens_effective, completion_ratio
**Our dimensions:** 6 attack surfaces, 16 prompt categories, 3-way classification, N models
**License note:** BB has no explicit license — author discretion on adaptation

### Session Setup

AI-Recommended approach with 3 techniques: Morphological Analysis (mapping BB components to our needs), SCAMPER (systematic adaptation decisions), Reverse Brainstorming (blind spot detection).

## Technique Selection

**Approach:** AI-Recommended Techniques
**Analysis Context:** Viewer adaptation with focus on minimal actionable changes

**Recommended Techniques:**

- **Morphological Analysis:** Map BB viewer components against our data dimensions to identify keep/adapt/drop/add decisions
- **SCAMPER Method:** Systematic adaptation of each viewer component using Substitute/Combine/Adapt/Modify/Put-to-use/Eliminate/Reverse
- **Reverse Brainstorming:** Surface blind spots by asking "how could we make this viewer terrible for our use case?"

**AI Rationale:** Practical adaptation task benefits from structured analysis over blue-sky ideation. Morphological mapping creates the foundation, SCAMPER provides specific change decisions, Reverse Brainstorming catches what we missed.

---

## Key Design Principles (established during session continuation)

1. **Rank by vulnerability, not resilience.** Most stuck = #1. This is an inverted leaderboard — celebrates failure, making it amusing.
2. **Surgical viewer changes.** Fork BB's viewer, change only what's needed. If it ain't broke don't fix it.
3. **Continuous metrics as sortable columns, not part of primary rank.** Avg tokens + stddev differentiate models with similar stuck rates.
4. **Filters over new visualizations.** Attack surfaces and prompt categories are filter dimensions, not heatmaps or extra columns. Let the leaderboard re-rank on filter toggle.

---

## Phase 1: Morphological Analysis — BB Component Mapping

### BB Viewer Architecture → AAAAAAAABench Mapping

| BB Component | BB Purpose | Decision | A-Trap Mapping |
|---|---|---|---|
| Hero leaderboard (stacked bars) | Ranks models best→worst, green/amber/red | **ADAPT** | Flip ranking: most stuck = #1. Green=stuck, orange=borderline, red=not_stuck |
| Filter bar (search, org, reasoning, technique, domain, outcome) | Slices both leaderboards | **ADAPT** | Map technique→prompt category, domain→attack surface, outcome→stuck/borderline/not_stuck |
| Detailed leaderboard table | Sortable columns, responds to filters | **ADAPT** | Add avg_tokens + token_stddev as sortable columns |
| Response drilldown | Click into individual responses | **KEEP** | Essential — people want to SEE the loops |
| Scatter plots (time/reasoning) | Correlation visualization | **DROP** | Would require historical run dates, not worth the effort |
| Domain heatmap | Per-category performance grid | **DROP** | Replaced by filter-based re-ranking (more powerful, less to build) |

### Filter Dimension Mapping

| BB Filter | AAAAAAAABench Equivalent |
|---|---|
| Benchmark Version | Run ID / date |
| Search | Model name, prompt id, prompt text |
| Org | Company (Anthropic, OpenAI, Google, etc.) |
| Reasoning | Thinking level (High/None) |
| Technique | Prompt Category (echo_trap, direct_request, counting, exhaustive_enum, etc. — 16 categories) |
| Domain | Attack Surface (pattern_momentum, counting_blindness, instruction_burial, compliance_trap, format_lock_in, snowball — 6 surfaces) |
| Outcome filter | Stuck / Borderline / Not Stuck |

**Key filter behavior:** Prompts tagged with multiple attack surfaces appear under ALL matching surface filters (inclusive OR).

### Ideas Generated

**[Leaderboard #1]**: Inverted Hero Leaderboard
_Concept_: Stacked bar leaderboard sorted by stuck rate descending. Green=stuck, orange=borderline, red=not_stuck. Most vulnerable model is #1. First thing visitors see.
_Novelty_: Flips typical "best model wins" framing — celebrates failure, making it amusing like BullshitBench.

**[Leaderboard #2]**: Detailed Sortable Table with Continuous Metrics
_Concept_: Full table with rank, model, company, thinking level, date, stuck%, borderline%, not_stuck%, avg_tokens, token_stddev, sample count. All columns sortable. Avg tokens and stddev are RAW values (not ratios) because that tells a more intuitive story.
_Novelty_: Continuous tiebreaker columns for differentiating models with similar stuck rates without mushing into ratios.

**[Filters #3]**: Attack Surface as Filter Dimension
_Concept_: Map BB's "Domain" filter to 6 attack surfaces. Inclusive OR on multi-tagged prompts. Both leaderboards re-rank when filtered.
_Novelty_: The re-ranking on filter toggle IS the insight — watch rankings shuffle between pattern_momentum and compliance_trap. No heatmap needed.

**[Filters #4]**: Prompt Category as Filter Dimension
_Concept_: Map BB's "Technique" filter to 16 prompt categories (echo_trap, counting, exhaustive_enum, etc.).
_Novelty_: Combined with surface filter gives two orthogonal slicing axes.

**[Drilldown #5]**: Response Drilldown — See the Loops
_Concept_: Click into individual responses to see actual stuck output — the wall of AAAA, the 10k-line count that never stops.
_Novelty_: Entertainment factor. People will want to SEE the loops. This is where the benchmark becomes shareable/viral.

---

## Phase 2: SCAMPER — Surgical Adaptation Decisions

### S — Substitute
- BB's semantic 3-way classification (pushback/partial/nonsense) with judge panels → our mechanical 3-way (stuck/borderline/not_stuck) based on finish_reason + token count. No judges, no grading panel, no judge disagreement. Simpler pipeline.

### C — Combine
- No extra work needed. BB already AND's multiple active filter dropdowns. Prompt category + attack surface filtering works out of the box.

### A — Adapt
- **Color scheme:** Green=stuck (lean into humor — "congrats, you're #1 at wasting API budget"), orange=borderline, red=not_stuck (refused/smart enough to stop).
- **Framing:** "AAAAAAAABench: Models That Can't Stop Repeating Themselves." Ranking the most expensive string generators.
- **Column labels:** Clinical for now — "Stuck / Borderline / Refused." Tagline TBD later.

### M — Modify
- Title and hero text adapted to our inverted humor framing
- BB's "Clear Pushback / Partial Challenge / Accepted Nonsense" labels → "Stuck / Borderline / Refused"

### E — Eliminate
- Judge selection UI (no judges in our pipeline)
- Scatter plots (would require historical run dates)
- Domain heatmap (replaced by filter-based re-ranking)
- BB-specific explainer text about grading methodology

### R — Reverse
- Primary ranking already flipped (most stuck = #1)
- Drilldown: leave BB's current implementation as-is, review later. No scope creep into "interesting refusal" highlighting.

---

## Phase 3: Reverse Brainstorming — Blind Spot Detection

"How could we make this viewer terrible for our use case?"

### Identified Blind Spots

**[Blind Spot #6]**: Giant Response Rendering
_Risk_: Stuck responses can be 36k tokens of raw "AAAA" or endless counting. BB never dealt with this — its responses are short. Rendering full text in drilldown could choke the browser.
_Fix_: Truncate response in drilldown with a "Show full response" toggle button. Surgical change to drilldown template.

**[Blind Spot #7]**: Array-valued Surface Filter
_Risk_: BB's domain filter likely expects a single string per response. Our prompts have `surfaces[]` as an array (compound prompts hit multiple surfaces). Filter logic will break on exact match.
_Fix_: Small tweak to filter logic — check array membership (includes) rather than equality.

**[Blind Spot #8]**: Small Sample Sizes per Filter Combo (DEFERRED)
_Risk_: Filtering to narrow intersections (e.g., pattern_momentum + echo_trap) could yield tiny sample sizes where percentages are meaningless. BB has the same issue.
_Decision_: Ignore for now. Same as BB.

---

## Implementation Plan

### Execution Order

#### Phase B: Data Plumbing (do first — nothing works without it)
1. Adapt data loader to consume our `responses.jsonl` schema instead of BB's grading format
2. Tweak filter logic for array-valued `surfaces[]` (includes vs equality check)
3. Wire prompt category → BB's "technique" filter slot
4. Wire attack surface → BB's "domain" filter slot

#### Phase A: Core Identity Changes
5. Flip sort order: stuck rate descending = rank #1
6. Swap colors: green=stuck, orange=borderline, red=refused
7. Swap stacked bar labels to "Stuck / Borderline / Refused"
8. Replace title/hero text ("AAAAAAAABench: Models That Can't Stop Repeating Themselves")
9. Strip: judge selection UI, scatter plots, domain heatmap, BB-specific explainer copy

#### Phase C: New Columns (parallel with D)
10. Add avg_tokens column to detailed table (mean completion_tokens per model)
11. Add token_stddev column to detailed table
12. Make both sortable

#### Phase D: Drilldown Fix (parallel with C)
13. Truncate long responses in drilldown view (stuck responses can be 36k tokens)
14. Add "Show full response" toggle button

### What NOT to Build
- No heatmap (filters replace it)
- No composite/weighted scoring (stuck_rate is the rank)
- No time-series scatter plots
- No "interesting refusal" analysis in drilldown
- No small-sample warnings
- No ratio-based continuous metrics (raw tokens + stddev instead)

## Session Summary

**Topic:** Adapting BullshitBench viewer for AAAAAAAABench result display
**Core Insight:** Flip the leaderboard — rank by vulnerability, not resilience. Most stuck = #1. Makes the benchmark both insightful and amusing, like BullshitBench.
**Techniques Used:** Morphological Analysis, SCAMPER, Reverse Brainstorming
**Ideas Generated:** 8 actionable items across 4 implementation themes
**Implementation:** 14 surgical changes to BB viewer, ordered B→A→C+D
