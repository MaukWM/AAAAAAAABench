# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AAAAAAAABench (A-Trap Benchmark) tests whether LLMs get stuck generating repetitive sequences of the letter "A". It sends prompts via OpenRouter and analyzes responses for A-trap indicators (high A-ratio, long consecutive A runs, length-cutoff while outputting A's).

The project is early-stage (v0.1). The `bullshit-benchmark/` directory is **reference material only** — it contains the mature BullshitBench codebase that serves as the methodological and infrastructure template for this benchmark. Copy patterns from it, but the active development target is the A-Trap benchmark.

## Commands

```bash
# Run collection (queries models via OpenRouter)
python3 scripts/a_trap_benchmark.py collect --config config.json

# Dry run (no API calls, writes placeholders)
python3 scripts/a_trap_benchmark.py collect --config config.json --dry-run

# Resume an interrupted run
python3 scripts/a_trap_benchmark.py collect --config config.json --resume --run-id <run_id>

# Filter by prompt category
python3 scripts/a_trap_benchmark.py collect --config config.json --categories echo_trap

# Override models from CLI
python3 scripts/a_trap_benchmark.py collect --models "anthropic/claude-sonnet-4,openai/gpt-4o-2024-08-06"
```

## Architecture

### Core Script: `scripts/a_trap_benchmark.py` (~2100 lines)

Single-file CLI derived from BullshitBench's `openrouter_benchmark.py`. Currently implements only the `collect` subcommand. Key sections:

- **Config + CLI**: `load_config()`, `apply_config_defaults()` — config.json values act as defaults, CLI flags override
- **OpenRouter client**: `OpenRouterClient` class using stdlib `urllib` (no requests/httpx dependency)
- **Rate limiting**: Model-aware requeue with exponential cooldown, jitter, and per-model inflight caps
- **Detection**: `detect_trap()` — three-way classification (stuck / borderline / not_stuck) based on `finish_reason` and `completion_tokens` relative to `max_tokens`
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
4. Each response passes through `detect_trap()` for inline stuck/borderline/not_stuck classification
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

Returns `{ classification, stuck, hit_token_limit, completion_tokens, max_tokens_effective, completion_ratio, total_chars }`. Three-way classification:
- **stuck**: `finish_reason == "length"` (hit token limit, could not stop)
- **borderline**: `finish_reason == "stop"` AND `completion_tokens >= borderline_ratio * max_tokens` (generated a lot but managed to stop)
- **not_stuck**: `finish_reason == "stop"` AND low token count (refused, brief response, or complied reasonably)

`borderline_ratio` (default 0.5) is configurable via `detection.borderline_ratio` in config.json.

## Tech Stack

Python 3, stdlib only (plus `python-dotenv`). No build system, no package manager. Vanilla HTML/JS for viewers (no build step).

## Reference: BullshitBench (`bullshit-benchmark/`)

The mature sibling benchmark. Useful patterns to follow when extending AAAAAAAABench:
- **Pipeline stages**: collect → grade → grade-panel → aggregate → publish (see `scripts/openrouter_benchmark.py`)
- **End-to-end orchestration**: Shell wrapper `scripts/run_end_to_end.sh`
- **Multi-judge grading**: 3-judge panel with mean consensus
- **Publishing**: Artifact normalization, leaderboard CSV generation, viewer dataset management
- **Viewer**: Self-contained HTML viewers in `viewer/`
