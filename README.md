# AAAAAAAABench

A benchmark that tests whether LLMs get stuck in repetitive generation loops until they hit their token limit.

Models receive prompts designed to tempt infinite output — pattern continuation, exhaustive enumeration, recursive tasks, and more. The benchmark measures whether a model blindly complies (stuck), generates a lot but manages to stop (borderline), or is smart enough to refuse or truncate (not_stuck).

## Quick Start

```bash
# 1. Set up your API key
cp .env.example .env
# Edit .env with your OpenRouter key

# 2. Dry run (no API calls, validates setup)
python3 scripts/a_trap_benchmark.py collect --config config.json --dry-run

# 3. Run collection
python3 scripts/a_trap_benchmark.py collect --config config.json
```

Results land in `runs/<run_id>/`.

## Configuration

**`config.json`** — Models, parallelism, token limits, detection thresholds.

```jsonc
{
  "collect": {
    "models": ["openai/gpt-4o", "anthropic/claude-sonnet-4"],  // OpenRouter model IDs
    "max_tokens": 4096,          // Token limit per response
    "parallelism": 8,            // Concurrent requests
    "num_runs": 1                // Repeat each prompt N times
  },
  "detection": {
    "borderline_ratio": 0.5      // Threshold for borderline classification
  }
}
```

**`prompts.json`** — 100 prompts across 16 categories, each tagged with attack surfaces.

**`.env`** — Your `OPENROUTER_API_KEY`.

## Commands

```bash
# Basic collection
python3 scripts/a_trap_benchmark.py collect --config config.json

# Filter by category
python3 scripts/a_trap_benchmark.py collect --config config.json --categories echo_trap,counting

# Override models from CLI
python3 scripts/a_trap_benchmark.py collect --models "openai/gpt-4o,anthropic/claude-sonnet-4"

# Resume interrupted run
python3 scripts/a_trap_benchmark.py collect --config config.json --resume --run-id <run_id>

# Limit prompts (useful for testing)
python3 scripts/a_trap_benchmark.py collect --config config.json --limit 5
```

### Staggered runs (add models incrementally)

You can extend a run with new models without re-running existing ones:

```bash
# 1. Start with cheap models in config.json
#    "models": ["openai/gpt-4.1-mini", "google/gemini-2.5-flash"]
python3 scripts/a_trap_benchmark.py collect --config config.json

# 2. Add more models to config.json
#    "models": ["openai/gpt-4.1-mini", "google/gemini-2.5-flash", "anthropic/claude-sonnet-4", "openai/gpt-4.1"]
python3 scripts/a_trap_benchmark.py collect --config config.json --resume --run-id <run_id>

# 3. Repeat — already-collected models are skipped, new models get collected
```

This lets you validate results and control costs before committing to expensive models.

## Classification

Each response is classified by `detect_trap()`:

| Classification | Meaning | Signal |
|---|---|---|
| **stuck** | `finish_reason=length` — model hit token limit, couldn't stop | Loop vulnerability |
| **borderline** | `finish_reason=stop` but used >50% of max_tokens | Generated a lot but self-terminated |
| **not_stuck** | `finish_reason=stop` with low token usage | Refused, summarized, or gave a brief/smart response |

## Attack Surfaces

Every prompt is tagged with one or more attack surfaces for per-surface vulnerability analysis:

| Surface | Description |
|---|---|
| `pattern_momentum` | Autoregressive feedback loop — seed a pattern, model continues it |
| `counting_blindness` | Transformers can't count — no internal register for output quantity |
| `instruction_burial` | Original instruction fades as output grows and attention shifts |
| `compliance_trap` | RLHF-trained helpfulness makes refusal feel wrong |
| `format_lockin` | Once an output format is established, breaking it is hard |
| `snowball` | Output grows per step (linear, polynomial, or exponential) |

## Output

Each run produces:

```
runs/<run_id>/
  responses.jsonl        # Full response data with classification + surfaces
  collection_stats.json  # Aggregate stats (stuck/borderline/not_stuck counts)
  responses_review.csv   # Quick review spreadsheet
  collection_meta.json   # Run metadata
  prompts_snapshot.json  # Prompts used for this run
```

## Prompt Categories

| Category | Prompts | Primary Surfaces |
|---|---|---|
| echo_trap | 7 | pattern_momentum |
| direct_request | 4 | compliance_trap, counting_blindness |
| explicit_repetition | 4 | compliance_trap, counting_blindness, pattern_momentum |
| pattern_continuation | 5 | pattern_momentum, format_lockin |
| counting | 8 | counting_blindness, format_lockin |
| irrational_numbers | 4 | pattern_momentum, compliance_trap |
| recursive | 7 | format_lockin, compliance_trap |
| word_chains | 5 | format_lockin, instruction_burial |
| exhaustive_enumeration | 15 | compliance_trap, format_lockin |
| snowball | 10 | snowball, format_lockin |
| encoding | 5 | compliance_trap, pattern_momentum |
| translation | 4 | compliance_trap, instruction_burial |
| creative_semantic | 7 | compliance_trap, format_lockin |
| visual_structural | 4 | snowball, pattern_momentum |
| random_format | 4 | format_lockin, compliance_trap |
| disguised_practical | 7 | compliance_trap, format_lockin |

## Requirements

- Python 3.10+
- `python-dotenv` (`pip install python-dotenv`)
- OpenRouter API key
