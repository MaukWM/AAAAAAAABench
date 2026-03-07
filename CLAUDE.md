# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HorseBench tests which LLMs are workhorses — models that keep galloping until they hit the token limit. It sends prompts via OpenRouter designed to tempt infinite output. Classifications: **workhorse** (ran til exhaustion), **halfhorse** (went far but stopped), **garfield** (too smart to fall for it).

The project is early-stage (v0.1). The `bullshit-benchmark/` directory is **reference material only** — it contains the mature BullshitBench codebase that serves as the methodological and infrastructure template for this benchmark.

## Commands

```bash
# Run collection (queries models via OpenRouter)
python3 scripts/horse_benchmark.py collect --config config.json

# Dry run (no API calls, writes placeholders)
python3 scripts/horse_benchmark.py collect --config config.json --dry-run

# Resume an interrupted run
python3 scripts/horse_benchmark.py collect --config config.json --resume --run-id <run_id>

# Filter by prompt category
python3 scripts/horse_benchmark.py collect --config config.json --categories echo_trap

# Override models from CLI
python3 scripts/horse_benchmark.py collect --models "anthropic/claude-sonnet-4,openai/gpt-4o-2024-08-06"
```

## Architecture

### Core Script: `scripts/horse_benchmark.py` (~2100 lines)

Single-file CLI derived from BullshitBench's `openrouter_benchmark.py`. Currently implements only the `collect` subcommand. Key sections:

- **Config + CLI**: `load_config()`, `apply_config_defaults()` — config.json values act as defaults, CLI flags override
- **OpenRouter client**: `OpenRouterClient` class using stdlib `urllib` (no requests/httpx dependency)
- **Rate limiting**: Model-aware requeue with exponential cooldown, jitter, and per-model inflight caps
- **Detection**: `detect_trap()` — three-way classification (workhorse / halfhorse / garfield) based on `finish_reason` and `completion_tokens` relative to `max_tokens`
- **Checkpointing**: `JsonlAppender` with configurable fsync for durable partial progress during long runs
- **Task building**: Cartesian product of models × prompts × num_runs, each getting a deterministic `sample_id`

### Configuration

- `config.json` — Model list, parallelism, rate limiting, detection thresholds, output paths
- `prompts.json` — Prompt definitions organized by category (`echo_trap`, `direct_request`)
- `.env` — `OPENROUTER_API_KEY` (required). See `.env.example`

### Data Flow

1. Prompts loaded from `prompts.json` (category-filtered if specified)
2. Tasks built as model × prompt × run_index combinations
3. Concurrent collection via thread pool with rate-limit-aware scheduling
4. Each response passes through `detect_trap()` for inline workhorse/halfhorse/garfield classification
5. Outputs written to `runs/<run_id>/`: `responses.jsonl`, `collection_stats.json`, `responses_review.csv`

### Prompt Format (`prompts.json`)

```json
{
  "categories": [
    {
      "category": "echo_trap",
      "prompts": [{ "id": "echo_1000a", "prompt": "AAA...", "description": "..." }]
    }
  ]
}
```

### Response Detection (`detect_trap`)

Returns `{ classification, workhorse, hit_token_limit, completion_tokens, max_tokens_effective, completion_ratio, total_chars }`. Three-way classification:
- **workhorse**: `finish_reason == "length"` (hit token limit, could not stop)
- **halfhorse**: `finish_reason == "stop"` AND `completion_tokens >= borderline_ratio * max_tokens` (generated a lot but managed to stop)
- **garfield**: `finish_reason == "stop"` AND low token count (refused, brief response, or complied reasonably)

`borderline_ratio` (default 0.5) is configurable via `detection.borderline_ratio` in config.json.

## Tech Stack

Python 3, stdlib only (plus `python-dotenv`). No build system, no package manager. Vanilla HTML/JS for viewers (no build step).

## Reference: BullshitBench (`bullshit-benchmark/`)

The mature sibling benchmark. Useful patterns to follow when extending HorseBench:
- **Pipeline stages**: collect → grade → grade-panel → aggregate → publish (see `scripts/openrouter_benchmark.py`)
- **End-to-end orchestration**: Shell wrapper `scripts/run_end_to_end.sh`
- **Multi-judge grading**: 3-judge panel with mean consensus
- **Publishing**: Artifact normalization, leaderboard CSV generation, viewer dataset management
- **Viewer**: Self-contained HTML viewers in `viewer/`
