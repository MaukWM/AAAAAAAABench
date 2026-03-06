#!/usr/bin/env python3
"""A-Trap Benchmark runner for OpenRouter.

Collect model responses and detect if models get stuck generating A's.
Based on BullshitBench infrastructure.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import datetime as dt
import hashlib
import json
import os
import pathlib
import random
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque
from email.utils import parsedate_to_datetime
from typing import Any

from dotenv import load_dotenv


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_RESPONSE_SYSTEM_PROMPT = "You are a helpful assistant."
EMPTY_MODEL_RESPONSE_PLACEHOLDER = "[Model returned an empty response.]"

REASONING_EFFORT_ALIASES: dict[str, str] = {}

REASONING_EFFORT_VALUES: tuple[str, ...] = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
)

REASONING_EFFORT_CLI_CHOICES: tuple[str, ...] = (
    "off",
    "minimal",
    "none",
    "low",
    "medium",
    "high",
    "xhigh",
)

COLLECT_DEFAULTS: dict[str, Any] = {
    "prompts": "prompts.json",
    "models": "",
    "models_file": "",
    "output_dir": "runs",
    "run_id": "",
    "num_runs": 1,
    "parallelism": 4,
    "max_inflight_per_model": 0,
    "limit": 0,
    "categories": "",
    "temperature": None,
    "max_tokens": 0,
    "empty_response_retries": 2,
    "pause_seconds": 0.0,
    "retries": 3,
    "timeout_seconds": 120,
    "response_system_prompt": DEFAULT_RESPONSE_SYSTEM_PROMPT,
    "omit_response_system_prompt": False,
    "response_reasoning_effort": "off",
    "model_reasoning_efforts": "",
    "store_request_messages": False,
    "store_response_raw": False,
    "shuffle_tasks": False,
    "seed": 42,
    "rate_limit_requeue": True,
    "rate_limit_cooldown_seconds": 20.0,
    "rate_limit_cooldown_max_seconds": 300.0,
    "rate_limit_cooldown_jitter_seconds": 1.0,
    "rate_limit_max_attempts": 12,
    "checkpoint_fsync_every": 20,
    "dry_run": False,
    "resume": False,
    "fail_on_error": True,
    "config": "config.json",
}


# =============================================================================
# CONFIG AND CLI HELPERS
# =============================================================================

def load_config(path: str) -> dict[str, Any]:
    config_path = pathlib.Path(path)
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Config JSON must be an object at top level.")
    return data


def cli_option_was_provided(args: argparse.Namespace, key: str) -> bool:
    raw_argv = getattr(args, "_raw_argv", None)
    if isinstance(raw_argv, list):
        argv = [str(item) for item in raw_argv]
    else:
        argv = [str(item) for item in sys.argv[1:]]

    option = f"--{key.replace('_', '-')}"
    negative_option = f"--no-{key.replace('_', '-')}"
    for token in argv:
        if token == option or token.startswith(option + "="):
            return True
        if token == negative_option or token.startswith(negative_option + "="):
            return True
    return False


def apply_config_defaults(
    args: argparse.Namespace,
    section: dict[str, Any],
    defaults: dict[str, Any],
) -> None:
    for key, default in defaults.items():
        if key == "config":
            continue
        if key not in section:
            continue
        if cli_option_was_provided(args, key):
            continue
        if not hasattr(args, key):
            continue
        current = getattr(args, key)
        if current == default:
            new_value = section[key]
            if key in {"models", "categories"} and isinstance(new_value, list):
                setattr(args, key, ",".join(str(x) for x in new_value))
            else:
                setattr(args, key, new_value)


# =============================================================================
# STRING AND DATA HELPERS
# =============================================================================

def split_csv(value: str) -> list[str]:
    if not value.strip():
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def normalize_reasoning_effort(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip().lower()
    if not cleaned or cleaned == "off":
        return None
    cleaned = REASONING_EFFORT_ALIASES.get(cleaned, cleaned)
    if cleaned not in REASONING_EFFORT_VALUES:
        allowed = ", ".join(REASONING_EFFORT_CLI_CHOICES)
        raise ValueError(f"{field_name} must be one of: {allowed}")
    return cleaned


def parse_model_reasoning_efforts(raw_value: Any) -> dict[str, list[str]]:
    if raw_value in ("", None):
        return {}

    parsed: Any
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "--model-reasoning-efforts must be a JSON object string."
            ) from exc
    elif isinstance(raw_value, dict):
        parsed = raw_value
    else:
        raise ValueError(
            "--model-reasoning-efforts must be empty, a JSON object string, or a JSON object."
        )

    if not isinstance(parsed, dict):
        raise ValueError("--model-reasoning-efforts must decode to a JSON object.")

    result: dict[str, list[str]] = {}
    for model, raw_efforts in parsed.items():
        model_id = str(model).strip()
        if not model_id:
            raise ValueError("--model-reasoning-efforts contains an empty model id.")
        effort_values: list[Any]
        if isinstance(raw_efforts, list):
            effort_values = raw_efforts
        else:
            effort_values = [raw_efforts]

        normalized: list[str] = []
        seen: set[str] = set()
        for raw_effort in effort_values:
            effort = normalize_reasoning_effort(
                raw_effort, field_name=f"reasoning effort for model {model_id}"
            )
            if effort is None:
                continue
            if effort not in seen:
                normalized.append(effort)
                seen.add(effort)
        result[model_id] = normalized
    return result


def build_model_variants(
    models: list[str],
    default_effort: str | None,
    per_model_efforts: dict[str, list[str]],
) -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []
    for model in models:
        if "/" in model:
            model_org, model_name = model.split("/", 1)
        else:
            model_org, model_name = "unknown", model

        configured = per_model_efforts.get(model)
        if configured is None:
            efforts: list[str | None] = [default_effort]
        elif configured:
            efforts = list(configured)
        else:
            efforts = [None]

        for effort in efforts:
            reasoning_level = effort if effort is not None else "default"
            model_row = f"{model_name}@reasoning={reasoning_level}"
            model_display = f"{model_org}/{model_row}"
            variants.append(
                {
                    "model_id": model,
                    "model_org": model_org,
                    "model_name": model_name,
                    "model_reasoning_level": reasoning_level,
                    "model_row": model_row,
                    "model_label": model_display,
                    "response_reasoning_effort": effort,
                }
            )
    return variants


def to_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")


def stable_short_hash(value: str, length: int = 12) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()
    return digest[:length]


def build_sample_id(
    *,
    run_id: str,
    prompt_id: str,
    model_label: str,
    run_index: int,
) -> str:
    run_slug = to_slug(run_id) or "run"
    model_slug = to_slug(model_label) or "model"
    model_key = f"{model_slug}_{stable_short_hash(model_label, length=10)}"
    return f"{run_slug}__{prompt_id}__{model_key}__run{run_index}"


# =============================================================================
# ARTIFACT DIRECTORY HELPERS
# =============================================================================

def resolve_new_artifact_dir(
    base_dir: pathlib.Path,
    preferred_id: str,
    *,
    explicit_id: bool,
    label: str,
) -> tuple[str, pathlib.Path]:
    base_dir.mkdir(parents=True, exist_ok=True)
    if explicit_id:
        artifact_dir = base_dir / preferred_id
        if artifact_dir.exists():
            raise ValueError(
                f"{label} already exists: {artifact_dir}. "
                "Choose a different explicit ID or omit the ID for auto-generated timestamp naming."
            )
        artifact_dir.mkdir(parents=True, exist_ok=False)
        return preferred_id, artifact_dir

    candidate_id = preferred_id
    artifact_dir = base_dir / candidate_id
    suffix = 1
    while artifact_dir.exists():
        candidate_id = f"{preferred_id}_{suffix:02d}"
        artifact_dir = base_dir / candidate_id
        suffix += 1
    artifact_dir.mkdir(parents=True, exist_ok=False)
    return candidate_id, artifact_dir


def resolve_artifact_dir(
    base_dir: pathlib.Path,
    preferred_id: str,
    *,
    explicit_id: bool,
    label: str,
    resume: bool,
) -> tuple[str, pathlib.Path]:
    if resume:
        if not explicit_id:
            raise ValueError(f"--resume requires explicit {label.lower()} via id flag.")
        artifact_dir = base_dir / preferred_id
        if not artifact_dir.exists():
            raise FileNotFoundError(
                f"Cannot resume {label.lower()} because it does not exist: {artifact_dir}"
            )
        if not artifact_dir.is_dir():
            raise ValueError(f"Expected directory for {label.lower()}: {artifact_dir}")
        return preferred_id, artifact_dir
    return resolve_new_artifact_dir(
        base_dir,
        preferred_id,
        explicit_id=explicit_id,
        label=label,
    )


# =============================================================================
# HTTP AND RETRY HELPERS
# =============================================================================

def is_retryable_http_status(status_code: int) -> bool:
    if status_code in (408, 409, 425, 429):
        return True
    return 500 <= status_code <= 599


def parse_retry_after_seconds(retry_after_header: str | None) -> float | None:
    if not retry_after_header:
        return None
    cleaned = retry_after_header.strip()
    if not cleaned:
        return None
    try:
        seconds = float(cleaned)
        if seconds >= 0:
            return seconds
    except ValueError:
        pass

    try:
        retry_after_time = parsedate_to_datetime(cleaned)
    except (TypeError, ValueError):
        return None
    if retry_after_time.tzinfo is None:
        retry_after_time = retry_after_time.replace(tzinfo=dt.timezone.utc)
    delay_seconds = (retry_after_time - dt.datetime.now(dt.timezone.utc)).total_seconds()
    if delay_seconds < 0:
        return 0.0
    return delay_seconds


def compute_retry_delay_seconds(attempt: int, retry_after_header: str | None = None) -> float:
    retry_after_seconds = parse_retry_after_seconds(retry_after_header)
    if retry_after_seconds is not None:
        return min(retry_after_seconds, 300.0)
    cap_seconds = min(float(2**attempt), 120.0)
    return random.uniform(0.0, cap_seconds)


def validate_retry_and_timeout(retries: int, timeout_seconds: int) -> None:
    if retries < 1:
        raise ValueError("--retries must be >= 1")
    if timeout_seconds < 1:
        raise ValueError("--timeout-seconds must be >= 1")


# =============================================================================
# CHECKPOINT AND VALIDATION HELPERS
# =============================================================================

def sample_id_from_row(row: dict[str, Any], *, context: str) -> str:
    sample_id = str(row.get("sample_id", "")).strip()
    if not sample_id:
        raise ValueError(f"{context} contains a row with empty sample_id.")
    return sample_id


def load_checkpoint_rows(path: pathlib.Path, *, context: str) -> tuple[list[dict[str, Any]], set[str]]:
    if not path.exists():
        return [], set()
    rows = read_jsonl(path)
    seen_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    for row in rows:
        sample_id = sample_id_from_row(row, context=context)
        if sample_id in seen_ids:
            duplicate_ids.add(sample_id)
        seen_ids.add(sample_id)
    if duplicate_ids:
        raise RuntimeError(
            f"{context} contains duplicate sample_id values. "
            f"duplicates={len(duplicate_ids)} sample={_sample_ids_summary(duplicate_ids)}"
        )
    return rows, seen_ids


def _sample_ids_summary(ids: set[str], limit: int = 5) -> str:
    if not ids:
        return ""
    sample = sorted(ids)[:limit]
    suffix = f" (+{len(ids) - limit} more)" if len(ids) > limit else ""
    return ", ".join(sample) + suffix


def validate_collect_integrity(
    tasks: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> None:
    expected_id_counts: dict[str, int] = defaultdict(int)
    for task in tasks:
        expected_id_counts[str(task.get("sample_id", "")).strip()] += 1
    duplicate_task_ids = {sample_id for sample_id, count in expected_id_counts.items() if count > 1}

    expected_ids = {str(task.get("sample_id", "")).strip() for task in tasks}
    if "" in expected_ids:
        raise RuntimeError("Collect task list contains empty sample_id.")
    if duplicate_task_ids:
        details = [
            "Collect task list contains duplicate sample_id values.",
            f"duplicates={len(duplicate_task_ids)}",
            f"sample={_sample_ids_summary(duplicate_task_ids)}",
        ]
        raise RuntimeError(" | ".join(details))

    seen_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    for row in records:
        sample_id = str(row.get("sample_id", "")).strip()
        if not sample_id:
            raise RuntimeError("Collect output contains a row with empty sample_id.")
        if sample_id in seen_ids:
            duplicate_ids.add(sample_id)
        seen_ids.add(sample_id)

    missing_ids = expected_ids - seen_ids
    unexpected_ids = seen_ids - expected_ids
    if duplicate_ids or missing_ids or unexpected_ids or len(records) != len(tasks):
        details: list[str] = [
            "Collect integrity check failed:",
            f"expected_rows={len(tasks)} actual_rows={len(records)}",
            f"duplicate_sample_ids={len(duplicate_ids)}",
            f"missing_sample_ids={len(missing_ids)}",
            f"unexpected_sample_ids={len(unexpected_ids)}",
        ]
        if duplicate_ids:
            details.append(f"duplicates: {_sample_ids_summary(duplicate_ids)}")
        if missing_ids:
            details.append(f"missing: {_sample_ids_summary(missing_ids)}")
        if unexpected_ids:
            details.append(f"unexpected: {_sample_ids_summary(unexpected_ids)}")
        raise RuntimeError(" | ".join(details))


# =============================================================================
# DATA LOADING
# =============================================================================

def load_models(models_csv: str, models_file: str) -> list[str]:
    models = split_csv(models_csv)
    if models_file:
        path = pathlib.Path(models_file)
        if not path.exists():
            raise FileNotFoundError(f"Models file not found: {models_file}")
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                cleaned = line.strip()
                if cleaned and not cleaned.startswith("#"):
                    models.append(cleaned)

    deduped: list[str] = []
    seen: set[str] = set()
    for model in models:
        if model not in seen:
            deduped.append(model)
            seen.add(model)

    if not deduped:
        raise ValueError("No models provided. Use --models and/or --models-file.")
    return deduped


def load_prompts(path: str, categories_filter: list[str], limit: int) -> list[dict[str, Any]]:
    """Load prompts from JSON file."""
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    categories = payload.get("categories")
    if not isinstance(categories, list):
        raise ValueError("prompts file must contain a top-level 'categories' array.")

    allowed = set(categories_filter)
    selected: list[dict[str, Any]] = []
    for category in categories:
        category_id = str(category.get("category", "")).strip()
        if allowed and category_id not in allowed:
            continue
        for prompt in category.get("prompts", []):
            selected.append(
                {
                    "id": prompt["id"],
                    "prompt": prompt["prompt"],
                    "description": prompt.get("description", ""),
                    "category": category_id,
                    "category_description": category.get("description", ""),
                    "surfaces": prompt["surfaces"],
                }
            )

    if limit > 0:
        selected = selected[:limit]
    if not selected:
        raise ValueError(
            "No prompts selected. Check --categories/--limit filters."
        )
    return selected


# =============================================================================
# JSON/JSONL I/O
# =============================================================================

def write_json(path: pathlib.Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_jsonl(path: pathlib.Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{lineno}: {exc}") from exc
            if not isinstance(parsed, dict):
                raise ValueError(f"Expected object JSON at {path}:{lineno}")
            rows.append(parsed)
    return rows


def append_jsonl(path: pathlib.Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


class JsonlAppender:
    def __init__(self, path: pathlib.Path, *, fsync_every: int = 0) -> None:
        self.path = path
        self.fsync_every = max(0, int(fsync_every))
        self._writes_since_sync = 0
        self._handle = path.open("a", encoding="utf-8", buffering=1)

    def append(self, row: dict[str, Any]) -> None:
        self._handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        if self.fsync_every <= 0:
            return
        self._writes_since_sync += 1
        if self._writes_since_sync >= self.fsync_every:
            self.sync()

    def sync(self) -> None:
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._writes_since_sync = 0

    def close(self) -> None:
        if self._handle.closed:
            return
        self._handle.flush()
        if self.fsync_every > 0:
            os.fsync(self._handle.fileno())
        self._handle.close()

    def __enter__(self) -> "JsonlAppender":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


# =============================================================================
# COERCION HELPERS
# =============================================================================

def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = float(text)
        except ValueError:
            return None
        if parsed.is_integer():
            return int(parsed)
    return None


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no"}:
            return False
    return None


# =============================================================================
# USAGE METRICS
# =============================================================================

def extract_response_usage_metrics(usage: Any) -> dict[str, Any]:
    usage_obj = usage if isinstance(usage, dict) else {}
    prompt_details = (
        usage_obj.get("prompt_tokens_details")
        if isinstance(usage_obj.get("prompt_tokens_details"), dict)
        else {}
    )
    completion_details = (
        usage_obj.get("completion_tokens_details")
        if isinstance(usage_obj.get("completion_tokens_details"), dict)
        else {}
    )
    cost_details = (
        usage_obj.get("cost_details")
        if isinstance(usage_obj.get("cost_details"), dict)
        else {}
    )
    return {
        "response_prompt_tokens": _coerce_int(usage_obj.get("prompt_tokens")),
        "response_completion_tokens": _coerce_int(usage_obj.get("completion_tokens")),
        "response_total_tokens": _coerce_int(usage_obj.get("total_tokens")),
        "response_reasoning_tokens": _coerce_int(
            completion_details.get("reasoning_tokens")
        ),
        "response_cached_prompt_tokens": _coerce_int(
            prompt_details.get("cached_tokens")
        ),
        "response_cache_write_tokens": _coerce_int(
            prompt_details.get("cache_write_tokens")
        ),
        "response_cost_usd": _coerce_float(usage_obj.get("cost")),
        "response_upstream_inference_cost_usd": _coerce_float(
            cost_details.get("upstream_inference_cost")
        ),
        "response_upstream_inference_prompt_cost_usd": _coerce_float(
            cost_details.get("upstream_inference_prompt_cost")
        ),
        "response_upstream_inference_completions_cost_usd": _coerce_float(
            cost_details.get("upstream_inference_completions_cost")
        ),
        "response_usage_is_byok": _coerce_bool(usage_obj.get("is_byok")),
    }


def enrich_collect_record_metrics(record: dict[str, Any]) -> dict[str, Any]:
    usage_metrics = extract_response_usage_metrics(record.get("response_usage", {}))
    record.update(usage_metrics)

    response_text = record.get("response_text", "")
    text = response_text if isinstance(response_text, str) else str(response_text or "")
    record["response_char_count"] = len(text)

    total_tokens = _coerce_int(record.get("response_total_tokens"))
    latency_ms = _coerce_int(record.get("response_latency_ms"))
    if total_tokens is not None and latency_ms is not None and latency_ms > 0:
        record["response_tokens_per_second"] = round(
            total_tokens / (latency_ms / 1000.0), 4
        )
    else:
        record["response_tokens_per_second"] = None
    return record


def _new_usage_bucket() -> dict[str, Any]:
    return {
        "rows": 0,
        "success_rows": 0,
        "error_rows": 0,
        "rows_with_usage": 0,
        "rows_with_total_tokens": 0,
        "rows_with_cost": 0,
        "rows_with_latency": 0,
        "rows_with_tokens_per_second": 0,
        "rows_with_byok_true": 0,
        "prompt_tokens_total": 0,
        "completion_tokens_total": 0,
        "total_tokens_total": 0,
        "reasoning_tokens_total": 0,
        "cached_prompt_tokens_total": 0,
        "cache_write_tokens_total": 0,
        "cost_usd_total": 0.0,
        "upstream_inference_cost_usd_total": 0.0,
        "upstream_inference_prompt_cost_usd_total": 0.0,
        "upstream_inference_completions_cost_usd_total": 0.0,
        "response_char_count_total": 0,
        "latency_ms_total": 0,
        "tokens_per_second_total": 0.0,
    }


def _add_if_int(bucket: dict[str, Any], key: str, value: Any) -> int | None:
    parsed = _coerce_int(value)
    if parsed is not None:
        bucket[key] += parsed
    return parsed


def _add_if_float(bucket: dict[str, Any], key: str, value: Any) -> float | None:
    parsed = _coerce_float(value)
    if parsed is not None:
        bucket[key] += parsed
    return parsed


def _finalize_usage_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    out = dict(bucket)
    rows_with_total_tokens = int(out["rows_with_total_tokens"])
    rows_with_latency = int(out["rows_with_latency"])
    rows_with_tokens_per_second = int(out["rows_with_tokens_per_second"])

    out["avg_total_tokens"] = (
        round(out["total_tokens_total"] / rows_with_total_tokens, 4)
        if rows_with_total_tokens > 0
        else None
    )
    out["avg_latency_ms"] = (
        round(out["latency_ms_total"] / rows_with_latency, 2)
        if rows_with_latency > 0
        else None
    )
    out["avg_tokens_per_second"] = (
        round(out["tokens_per_second_total"] / rows_with_tokens_per_second, 4)
        if rows_with_tokens_per_second > 0
        else None
    )

    out["cost_usd_total"] = round(float(out["cost_usd_total"]), 8)
    out["upstream_inference_cost_usd_total"] = round(
        float(out["upstream_inference_cost_usd_total"]), 8
    )
    out["upstream_inference_prompt_cost_usd_total"] = round(
        float(out["upstream_inference_prompt_cost_usd_total"]), 8
    )
    out["upstream_inference_completions_cost_usd_total"] = round(
        float(out["upstream_inference_completions_cost_usd_total"]), 8
    )
    out["tokens_per_second_total"] = round(float(out["tokens_per_second_total"]), 6)
    return out


def summarize_collect_usage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    overall = _new_usage_bucket()
    by_model: dict[str, dict[str, Any]] = defaultdict(_new_usage_bucket)

    for row in rows:
        model = str(row.get("model", ""))
        buckets = [overall, by_model[model]]

        has_usage = isinstance(row.get("response_usage"), dict) and bool(
            row.get("response_usage")
        )
        is_error = bool(row.get("error"))
        byok = _coerce_bool(row.get("response_usage_is_byok"))

        for bucket in buckets:
            bucket["rows"] += 1
            if is_error:
                bucket["error_rows"] += 1
            else:
                bucket["success_rows"] += 1
            if has_usage:
                bucket["rows_with_usage"] += 1
            if byok is True:
                bucket["rows_with_byok_true"] += 1

            _add_if_int(bucket, "prompt_tokens_total", row.get("response_prompt_tokens"))
            _add_if_int(
                bucket, "completion_tokens_total", row.get("response_completion_tokens")
            )
            total_tokens = _add_if_int(
                bucket, "total_tokens_total", row.get("response_total_tokens")
            )
            if total_tokens is not None:
                bucket["rows_with_total_tokens"] += 1
            _add_if_int(
                bucket, "reasoning_tokens_total", row.get("response_reasoning_tokens")
            )
            _add_if_int(
                bucket,
                "cached_prompt_tokens_total",
                row.get("response_cached_prompt_tokens"),
            )
            _add_if_int(
                bucket,
                "cache_write_tokens_total",
                row.get("response_cache_write_tokens"),
            )
            cost = _add_if_float(bucket, "cost_usd_total", row.get("response_cost_usd"))
            if cost is not None:
                bucket["rows_with_cost"] += 1
            _add_if_float(
                bucket,
                "upstream_inference_cost_usd_total",
                row.get("response_upstream_inference_cost_usd"),
            )
            _add_if_float(
                bucket,
                "upstream_inference_prompt_cost_usd_total",
                row.get("response_upstream_inference_prompt_cost_usd"),
            )
            _add_if_float(
                bucket,
                "upstream_inference_completions_cost_usd_total",
                row.get("response_upstream_inference_completions_cost_usd"),
            )
            _add_if_int(
                bucket, "response_char_count_total", row.get("response_char_count")
            )
            latency_ms = _add_if_int(bucket, "latency_ms_total", row.get("response_latency_ms"))
            if latency_ms is not None:
                bucket["rows_with_latency"] += 1
            tps = _add_if_float(
                bucket, "tokens_per_second_total", row.get("response_tokens_per_second")
            )
            if tps is not None:
                bucket["rows_with_tokens_per_second"] += 1

    by_model_rows = [
        {"model": model, **_finalize_usage_bucket(bucket)}
        for model, bucket in by_model.items()
    ]
    by_model_rows.sort(
        key=lambda row: (
            -int(row.get("total_tokens_total", 0) or 0),
            str(row.get("model", "")),
        )
    )
    return {
        "overall": _finalize_usage_bucket(overall),
        "by_model": by_model_rows,
    }


def is_rate_limit_error_record(row: dict[str, Any]) -> bool:
    if str(row.get("error_kind", "")).strip() == "rate_limit":
        return True
    status = _coerce_int(row.get("error_http_status"))
    if status == 429:
        return True
    error_text = str(row.get("error", "")).lower()
    return ("http 429" in error_text) or ("rate limit" in error_text)


def write_collect_review_csv(path: pathlib.Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "status",
        "error",
        "sample_id",
        "model",
        "model_id",
        "model_org",
        "model_name",
        "model_reasoning_level",
        "model_row",
        "response_reasoning_effort",
        "run_index",
        "prompt_id",
        "category",
        "response_latency_ms",
        "response_prompt_tokens",
        "response_completion_tokens",
        "response_total_tokens",
        "response_reasoning_tokens",
        "response_cached_prompt_tokens",
        "response_cache_write_tokens",
        "response_cost_usd",
        "response_char_count",
        "response_tokens_per_second",
        "error_kind",
        "error_http_status",
        "error_retryable",
        "error_retry_after_seconds",
        "response_finish_reason",
        "warnings",
        "detection_classification",
        "detection_stuck",
        "detection_hit_token_limit",
        "detection_completion_tokens",
        "detection_reasoning_tokens",
        "detection_output_tokens",
        "detection_max_tokens_effective",
        "detection_completion_ratio",
        "detection_total_chars",
        "response_text",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            detection = row.get("detection", {})
            writer.writerow(
                {
                    "status": "error" if row.get("error") else "ok",
                    "error": row.get("error", ""),
                    "sample_id": row.get("sample_id", ""),
                    "model": row.get("model", ""),
                    "model_id": row.get("model_id", ""),
                    "model_org": row.get("model_org", ""),
                    "model_name": row.get("model_name", ""),
                    "model_reasoning_level": row.get("model_reasoning_level", ""),
                    "model_row": row.get("model_row", ""),
                    "response_reasoning_effort": row.get("response_reasoning_effort", ""),
                    "run_index": row.get("run_index", ""),
                    "prompt_id": row.get("prompt_id", ""),
                    "category": row.get("category", ""),
                    "response_latency_ms": row.get("response_latency_ms", ""),
                    "response_prompt_tokens": row.get("response_prompt_tokens", ""),
                    "response_completion_tokens": row.get("response_completion_tokens", ""),
                    "response_total_tokens": row.get("response_total_tokens", ""),
                    "response_reasoning_tokens": row.get("response_reasoning_tokens", ""),
                    "response_cached_prompt_tokens": row.get("response_cached_prompt_tokens", ""),
                    "response_cache_write_tokens": row.get("response_cache_write_tokens", ""),
                    "response_cost_usd": row.get("response_cost_usd", ""),
                    "response_char_count": row.get("response_char_count", ""),
                    "response_tokens_per_second": row.get("response_tokens_per_second", ""),
                    "error_kind": row.get("error_kind", ""),
                    "error_http_status": row.get("error_http_status", ""),
                    "error_retryable": row.get("error_retryable", ""),
                    "error_retry_after_seconds": row.get("error_retry_after_seconds", ""),
                    "response_finish_reason": row.get("response_finish_reason", ""),
                    "warnings": "; ".join(str(x) for x in row.get("warnings", [])),
                    "detection_classification": detection.get("classification", ""),
                    "detection_stuck": detection.get("stuck", ""),
                    "detection_hit_token_limit": detection.get("hit_token_limit", ""),
                    "detection_completion_tokens": detection.get("completion_tokens", ""),
                    "detection_reasoning_tokens": detection.get("reasoning_tokens", ""),
                    "detection_output_tokens": detection.get("output_tokens", ""),
                    "detection_max_tokens_effective": detection.get("max_tokens_effective", ""),
                    "detection_completion_ratio": detection.get("completion_ratio", ""),
                    "detection_total_chars": detection.get("total_chars", ""),
                    "response_text": row.get("response_text", ""),
                }
            )


# =============================================================================
# OPENROUTER CLIENT
# =============================================================================

def normalize_message_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks: list[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    chunks.append(text)
        return "\n".join(chunks).strip()
    return str(content).strip()


class OpenRouterAPIError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


class OpenRouterClient:
    def __init__(self, api_key: str, timeout_seconds: int) -> None:
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be >= 1")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.referer = os.getenv("OPENROUTER_REFERER", "")
        self.app_name = os.getenv("OPENROUTER_APP_NAME", "a-trap-benchmark")

    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float | None,
        max_tokens: int,
        retries: int,
        extra_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens > 0:
            payload["max_tokens"] = max_tokens
        if extra_payload:
            payload.update(extra_payload)
        encoded = json.dumps(payload).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": self.app_name,
        }
        if self.referer:
            headers["HTTP-Referer"] = self.referer

        if retries < 1:
            raise ValueError("retries must be >= 1")

        last_error: Exception | None = None
        for attempt in range(1, retries + 1):
            retry_after_header: str | None = None
            retry_after_seconds: float | None = None
            request = urllib.request.Request(
                self.base_url,
                data=encoded,
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as resp:
                    raw = resp.read().decode("utf-8")
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    raise RuntimeError("OpenRouter returned non-object JSON.")
                return parsed
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="ignore")
                retry_after_header = exc.headers.get("Retry-After") if exc.headers else None
                retry_after_seconds = parse_retry_after_seconds(retry_after_header)
                retryable = is_retryable_http_status(exc.code)
                last_error = OpenRouterAPIError(
                    f"HTTP {exc.code} from OpenRouter (attempt {attempt}/{retries})"
                    f"{' [retryable]' if retryable else ' [non-retryable]'}: {detail}"
                    + (
                        f" (retry_after_seconds={retry_after_seconds})"
                        if retry_after_seconds is not None
                        else ""
                    ),
                    status_code=exc.code,
                    retryable=retryable,
                    retry_after_seconds=retry_after_seconds,
                )
                if not retryable:
                    raise last_error from exc
            except Exception as exc:
                last_error = RuntimeError(
                    f"OpenRouter call failed (attempt {attempt}/{retries}): {exc}"
                )

            if attempt < retries:
                time.sleep(compute_retry_delay_seconds(attempt, retry_after_header))

        assert last_error is not None
        raise last_error


def extract_model_text(api_response: dict[str, Any]) -> str:
    if api_response.get("error"):
        err = api_response.get("error")
        raise RuntimeError(f"API returned error payload: {json.dumps(err, ensure_ascii=False)}")

    choices = api_response.get("choices", [])
    if not choices or not isinstance(choices, list):
        raise RuntimeError("API response missing choices array.")
    first_choice = choices[0] if choices else {}
    if not isinstance(first_choice, dict):
        raise RuntimeError("API response first choice is not an object.")
    message = first_choice.get("message", {})
    if not isinstance(message, dict):
        raise RuntimeError("API response choice.message is not an object.")
    return normalize_message_content(message.get("content", ""))


def extract_message_refusal(api_response: dict[str, Any]) -> str:
    choices = api_response.get("choices", [])
    if not choices or not isinstance(choices, list):
        return ""
    first_choice = choices[0] if choices else {}
    if not isinstance(first_choice, dict):
        return ""
    message = first_choice.get("message", {})
    if not isinstance(message, dict):
        return ""
    return normalize_message_content(message.get("refusal", ""))


def extract_finish_reason(api_response: dict[str, Any]) -> str | None:
    choices = api_response.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return None
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return None
    finish_reason = first_choice.get("finish_reason")
    return str(finish_reason) if finish_reason is not None else None


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


# =============================================================================
# TRAP DETECTION
# =============================================================================

def detect_trap(
    response: str,
    finish_reason: str | None = None,
    completion_tokens: int | None = None,
    reasoning_tokens: int | None = None,
    max_tokens: int = 0,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify response as stuck / borderline / not_stuck.

    Classification rules:
    - stuck:     finish_reason == "length" (hit token limit, could not stop)
    - borderline: finish_reason == "stop" AND output_tokens >= borderline_ratio * max_tokens
    - not_stuck: finish_reason == "stop" AND low token count

    For reasoning models, output_tokens = completion_tokens - reasoning_tokens
    (we only count visible output, not internal thinking).
    """
    cfg = thresholds or {}
    borderline_ratio = cfg.get("borderline_ratio", 0.5)

    hit_token_limit = (finish_reason == "length")
    total_chars = len(response)

    # Subtract reasoning tokens to get visible output tokens
    if completion_tokens is not None and reasoning_tokens:
        output_tokens = max(completion_tokens - reasoning_tokens, 0)
    else:
        output_tokens = completion_tokens

    max_tokens_effective = max_tokens if max_tokens > 0 else 0
    completion_ratio = (
        round(output_tokens / max_tokens_effective, 4)
        if output_tokens is not None and max_tokens_effective > 0
        else None
    )

    if hit_token_limit:
        classification = "stuck"
    elif (
        completion_ratio is not None
        and completion_ratio >= borderline_ratio
    ):
        classification = "borderline"
    else:
        classification = "not_stuck"

    return {
        "classification": classification,
        "stuck": classification == "stuck",
        "hit_token_limit": hit_token_limit,
        "completion_tokens": completion_tokens,
        "reasoning_tokens": reasoning_tokens,
        "output_tokens": output_tokens,
        "max_tokens_effective": max_tokens_effective,
        "completion_ratio": completion_ratio,
        "total_chars": total_chars,
    }


# =============================================================================
# TASK BUILDING AND COLLECTION
# =============================================================================

def build_collect_tasks(
    model_variants: list[dict[str, Any]],
    prompts: list[dict[str, Any]],
    num_runs: int,
    run_id: str,
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for run_index in range(1, num_runs + 1):
        for variant in model_variants:
            model_id = str(variant["model_id"])
            model_org = str(variant.get("model_org", "unknown"))
            model_name = str(variant.get("model_name", model_id))
            model_reasoning_level = str(variant.get("model_reasoning_level", "default"))
            model_row = str(
                variant.get("model_row", f"{model_name}@reasoning={model_reasoning_level}")
            )
            model_label = str(variant["model_label"])
            effort = variant.get("response_reasoning_effort")
            for prompt in prompts:
                sample_id = build_sample_id(
                    run_id=run_id,
                    prompt_id=str(prompt["id"]),
                    model_label=model_label,
                    run_index=run_index,
                )
                tasks.append(
                    {
                        "sample_id": sample_id,
                        "run_index": run_index,
                        "model": model_label,
                        "model_id": model_id,
                        "model_org": model_org,
                        "model_name": model_name,
                        "model_reasoning_level": model_reasoning_level,
                        "model_row": model_row,
                        "response_reasoning_effort": effort,
                        "prompt": prompt,
                    }
                )
    return tasks


def collect_one(
    task: dict[str, Any],
    *,
    client: OpenRouterClient | None,
    system_prompt: str,
    omit_system_prompt: bool,
    temperature: float | None,
    max_tokens: int,
    empty_response_retries: int,
    retries: int,
    pause_seconds: float,
    dry_run: bool,
    store_request_messages: bool,
    store_response_raw: bool,
    detection_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prompt = task["prompt"]
    started_at = utc_now_iso()
    t0 = time.perf_counter()
    request_messages: list[dict[str, str]] = []
    if not omit_system_prompt and system_prompt.strip():
        request_messages.append({"role": "system", "content": system_prompt})
    request_messages.append({"role": "user", "content": prompt["prompt"]})

    reasoning_effort = task.get("response_reasoning_effort")
    effort_value = (
        str(reasoning_effort).strip()
        if isinstance(reasoning_effort, str) and reasoning_effort.strip()
        else None
    )
    model_reasoning_level = str(
        task.get("model_reasoning_level", effort_value if effort_value is not None else "default")
    )
    model_row = str(
        task.get(
            "model_row",
            f"{task.get('model_name', task.get('model_id', task['model']))}"
            f"@reasoning={model_reasoning_level}",
        )
    )

    record: dict[str, Any] = {
        "sample_id": task["sample_id"],
        "run_index": task["run_index"],
        "model": task["model"],
        "model_id": task.get("model_id", task["model"]),
        "model_org": task.get("model_org", "unknown"),
        "model_name": task.get("model_name", task.get("model_id", task["model"])),
        "model_reasoning_level": model_reasoning_level,
        "model_row": model_row,
        "response_reasoning_effort": effort_value,
        "prompt_id": prompt["id"],
        "category": prompt["category"],
        "surfaces": prompt["surfaces"],
        "prompt_text": prompt["prompt"],
        "prompt_description": prompt.get("description", ""),
        "stateless_request": True,
        "request_messages": request_messages if store_request_messages else [],
        "response_text": "",
        "response_id": "",
        "response_usage": {},
        "response_latency_ms": None,
        "response_created": None,
        "response_finish_reason": None,
        "warnings": [],
        "response_raw": None,
        "started_at_utc": started_at,
        "finished_at_utc": None,
        "error_kind": "",
        "error_http_status": None,
        "error_retryable": None,
        "error_retry_after_seconds": None,
        "error": "",
        "detection": {},
    }
    enrich_collect_record_metrics(record)

    try:
        if pause_seconds > 0:
            time.sleep(pause_seconds)

        effective_max_tokens = max_tokens

        if dry_run:
            response_text = (
                f"DRY RUN response for prompt={prompt['id']} model={task['model']}"
            )
            payload: dict[str, Any] = {
                "id": "dry-run",
                "created": None,
                "usage": {},
                "choices": [{"finish_reason": "stop"}],
            }
        else:
            assert client is not None
            extra_payload: dict[str, Any] | None = None
            if effort_value is not None:
                extra_payload = {
                    "reasoning": {"effort": effort_value},
                    "provider": {"require_parameters": True},
                }
            empty_attempt = 0
            payload = {}
            while True:
                try:
                    payload = client.chat(
                        model=task.get("model_id", task["model"]),
                        messages=request_messages,
                        temperature=temperature,
                        max_tokens=effective_max_tokens,
                        retries=retries,
                        extra_payload=extra_payload,
                    )
                except OpenRouterAPIError as exc:
                    if (
                        exc.status_code == 402
                        and "fewer max_tokens" in str(exc).lower()
                    ):
                        if effective_max_tokens <= 0:
                            next_max_tokens = 1024
                        elif effective_max_tokens > 128:
                            next_max_tokens = max(128, effective_max_tokens // 2)
                        else:
                            raise
                        if next_max_tokens == effective_max_tokens:
                            raise
                        record["warnings"].append(
                            "max_tokens_auto_reduced_after_402="
                            f"{effective_max_tokens}->{next_max_tokens}"
                        )
                        effective_max_tokens = next_max_tokens
                        continue
                    raise
                if store_response_raw:
                    record["response_raw"] = payload
                response_text = extract_model_text(payload)
                if response_text.strip():
                    break

                refusal_text = extract_message_refusal(payload)
                if refusal_text.strip():
                    response_text = refusal_text
                    record["warnings"].append("response_text_fallback=message.refusal")
                    break

                finish_reason = extract_finish_reason(payload)
                if empty_attempt < empty_response_retries:
                    empty_attempt += 1
                    continue

                response_text = EMPTY_MODEL_RESPONSE_PLACEHOLDER
                record["warnings"].append(
                    "response_text_fallback=empty_placeholder"
                )
                if finish_reason is not None:
                    record["warnings"].append(
                        f"empty_response_finish_reason={finish_reason}"
                    )
                break

        record["response_text"] = response_text
        record["response_id"] = str(payload.get("id", ""))
        record["response_created"] = payload.get("created")
        record["response_usage"] = payload.get("usage", {})
        record["response_finish_reason"] = extract_finish_reason(payload)
        if record["response_finish_reason"] == "length":
            record["warnings"].append("response_finish_reason=length (possible truncation)")
        if store_response_raw and record["response_raw"] is None:
            record["response_raw"] = payload

        # Trap detection
        usage = payload.get("usage", {})
        completion_tokens_details = usage.get("completion_tokens_details") or {}
        record["detection"] = detect_trap(
            response_text,
            finish_reason=record["response_finish_reason"],
            completion_tokens=usage.get("completion_tokens"),
            reasoning_tokens=completion_tokens_details.get("reasoning_tokens"),
            max_tokens=effective_max_tokens,
            thresholds=detection_config,
        )

    except Exception as exc:
        record["error"] = str(exc)
        if isinstance(exc, OpenRouterAPIError):
            status_code = exc.status_code
            record["error_http_status"] = status_code
            record["error_retryable"] = exc.retryable
            record["error_retry_after_seconds"] = exc.retry_after_seconds
            record["error_kind"] = "rate_limit" if status_code == 429 else "api_error"
        else:
            record["error_kind"] = "runtime_error"
    finally:
        record["response_latency_ms"] = int((time.perf_counter() - t0) * 1000)
        record["finished_at_utc"] = utc_now_iso()
        enrich_collect_record_metrics(record)

    return record


def run_collect(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    collect_config = config.get("collect", {}) if isinstance(config, dict) else {}
    if not isinstance(collect_config, dict):
        raise ValueError("Config key 'collect' must be an object.")
    if not bool(getattr(args, "_skip_config_defaults", False)):
        apply_config_defaults(args, collect_config, COLLECT_DEFAULTS)

    if args.resume and not args.run_id.strip():
        raise ValueError("--resume for collect requires --run-id.")
    if args.num_runs < 1:
        raise ValueError("--num-runs must be >= 1")
    if args.parallelism < 1:
        raise ValueError("--parallelism must be >= 1")
    if args.max_inflight_per_model < 0:
        raise ValueError("--max-inflight-per-model must be >= 0")
    if args.rate_limit_max_attempts < 1:
        raise ValueError("--rate-limit-max-attempts must be >= 1")
    if args.rate_limit_cooldown_seconds < 0:
        raise ValueError("--rate-limit-cooldown-seconds must be >= 0")
    if args.rate_limit_cooldown_max_seconds < 0:
        raise ValueError("--rate-limit-cooldown-max-seconds must be >= 0")
    if args.rate_limit_cooldown_jitter_seconds < 0:
        raise ValueError("--rate-limit-cooldown-jitter-seconds must be >= 0")
    if args.checkpoint_fsync_every < 0:
        raise ValueError("--checkpoint-fsync-every must be >= 0")
    if args.empty_response_retries < 0:
        raise ValueError("--empty-response-retries must be >= 0")
    validate_retry_and_timeout(args.retries, args.timeout_seconds)

    models = load_models(args.models, args.models_file)
    base_reasoning_effort = normalize_reasoning_effort(
        args.response_reasoning_effort, field_name="--response-reasoning-effort"
    )
    per_model_reasoning_efforts = parse_model_reasoning_efforts(
        args.model_reasoning_efforts
    )
    unknown_reasoning_models = set(per_model_reasoning_efforts.keys()) - set(models)
    if unknown_reasoning_models:
        if cli_option_was_provided(args, "model_reasoning_efforts"):
            unknown_sorted = ", ".join(sorted(unknown_reasoning_models))
            raise ValueError(
                "model_reasoning_efforts contains model(s) not in selected models: "
                f"{unknown_sorted}"
            )
        for unknown_model in unknown_reasoning_models:
            per_model_reasoning_efforts.pop(unknown_model, None)
        print(
            "Ignoring config model_reasoning_efforts for models not in current --models "
            f"selection: {', '.join(sorted(unknown_reasoning_models))}",
            flush=True,
        )
    model_variants = build_model_variants(
        models, base_reasoning_effort, per_model_reasoning_efforts
    )
    omit_system_prompt = bool(args.omit_response_system_prompt) or not str(
        args.response_system_prompt
    ).strip()
    categories_filter = split_csv(args.categories)
    prompts = load_prompts(args.prompts, categories_filter, args.limit)
    detection_config = config.get("detection", {})

    timestamp = dt.datetime.now(dt.timezone.utc)
    run_seed_id = args.run_id.strip() or timestamp.strftime("%Y%m%d_%H%M%S")
    run_id, run_dir = resolve_artifact_dir(
        pathlib.Path(args.output_dir),
        run_seed_id,
        explicit_id=bool(args.run_id.strip()),
        label="Run ID",
        resume=bool(args.resume),
    )

    tasks = build_collect_tasks(
        model_variants,
        prompts,
        args.num_runs,
        run_id=run_id,
    )
    if args.shuffle_tasks:
        rng = random.Random(args.seed)
        rng.shuffle(tasks)

    task_ids = {sample_id_from_row(task, context="Collect task list") for task in tasks}
    partial_responses_path = run_dir / "responses.partial.jsonl"
    final_responses_path = run_dir / "responses.jsonl"

    checkpoint_records: list[dict[str, Any]] = []
    checkpoint_ids: set[str] = set()
    if args.resume:
        checkpoint_source = partial_responses_path
        if not checkpoint_source.exists() and final_responses_path.exists():
            checkpoint_source = final_responses_path
        checkpoint_records, checkpoint_ids = load_checkpoint_rows(
            checkpoint_source,
            context=f"Collect checkpoint {checkpoint_source}",
        )
        unexpected_checkpoint_ids = checkpoint_ids - task_ids
        if unexpected_checkpoint_ids:
            # This is so that we can slowly add more models as we measure cost
            print(
                f"Resume: {len(unexpected_checkpoint_ids)} checkpoint responses not in "
                f"current task set (models/prompts changed since original run). "
                f"Keeping them in output. sample={_sample_ids_summary(unexpected_checkpoint_ids)}"
            )
        if checkpoint_records and checkpoint_source != partial_responses_path:
            write_jsonl(partial_responses_path, checkpoint_records)
    for checkpoint_row in checkpoint_records:
        enrich_collect_record_metrics(checkpoint_row)

    tasks_to_run = [
        task
        for task in tasks
        if sample_id_from_row(task, context="Collect task list") not in checkpoint_ids
    ]

    collection_meta = {
        "phase": "collect",
        "run_id": run_id,
        "timestamp_utc": timestamp.isoformat(),
        "resumed": bool(args.resume),
        "resumed_completed_rows": len(checkpoint_records),
        "prompts_path": str(pathlib.Path(args.prompts).resolve()),
        "prompt_count": len(prompts),
        "models": models,
        "model_variants": model_variants,
        "num_runs": args.num_runs,
        "task_count": len(tasks),
        "parallelism": args.parallelism,
        "max_inflight_per_model": args.max_inflight_per_model,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "response_system_prompt": None
        if omit_system_prompt
        else args.response_system_prompt,
        "omit_response_system_prompt": omit_system_prompt,
        "response_reasoning_effort": base_reasoning_effort,
        "model_reasoning_efforts": per_model_reasoning_efforts,
        "store_request_messages": bool(args.store_request_messages),
        "store_response_raw": bool(args.store_response_raw),
        "retries": args.retries,
        "timeout_seconds": args.timeout_seconds,
        "categories_filter": categories_filter,
        "shuffle_tasks": bool(args.shuffle_tasks),
        "seed": args.seed,
        "rate_limit_requeue": bool(args.rate_limit_requeue),
        "rate_limit_cooldown_seconds": args.rate_limit_cooldown_seconds,
        "rate_limit_cooldown_max_seconds": args.rate_limit_cooldown_max_seconds,
        "rate_limit_cooldown_jitter_seconds": args.rate_limit_cooldown_jitter_seconds,
        "rate_limit_max_attempts": args.rate_limit_max_attempts,
        "checkpoint_fsync_every": args.checkpoint_fsync_every,
        "dry_run": bool(args.dry_run),
        "stateless_request": True,
        "fail_on_error": bool(args.fail_on_error),
        "config_path": str(pathlib.Path(args.config).resolve()),
    }
    write_json(run_dir / "collection_meta.json", collection_meta)
    write_json(run_dir / "prompts_snapshot.json", prompts)
    collect_events_path = run_dir / "collect_events.jsonl"
    if not args.resume:
        collect_events_path.write_text("", encoding="utf-8")
    elif not collect_events_path.exists():
        collect_events_path.write_text("", encoding="utf-8")
    client: OpenRouterClient | None = None
    if not args.dry_run:
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required unless --dry-run is set.")
        client = OpenRouterClient(api_key=api_key, timeout_seconds=args.timeout_seconds)

    started = time.perf_counter()
    records: list[dict[str, Any]] = list(checkpoint_records)
    total = len(tasks)
    completed = len(checkpoint_records)
    attempt_count = 0
    rate_limit_requeue_count = 0
    final_rate_limit_error_count = 0
    task_attempts: dict[str, int] = defaultdict(int)

    with JsonlAppender(
        partial_responses_path, fsync_every=args.checkpoint_fsync_every
    ) as partial_writer, JsonlAppender(
        collect_events_path, fsync_every=args.checkpoint_fsync_every
    ) as events_writer:
        events_writer.append(
            {
                "timestamp_utc": utc_now_iso(),
                "phase": "collect",
                "event": "resume_start" if args.resume else "start",
                "run_id": run_id,
                "checkpoint_rows": len(checkpoint_records),
                "remaining_rows": len(tasks_to_run),
            }
        )

        if tasks_to_run:
            pending_by_model: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
            for task in tasks_to_run:
                pending_by_model[str(task.get("model", ""))].append(task)
            model_order = sorted(pending_by_model.keys())
            model_next_ready_at: dict[str, float] = defaultdict(float)
            model_in_flight: dict[str, int] = defaultdict(int)
            round_robin_index = 0

            def pending_task_count() -> int:
                return sum(len(queue) for queue in pending_by_model.values())

            def model_can_submit(model: str) -> bool:
                if args.max_inflight_per_model <= 0:
                    return True
                return model_in_flight.get(model, 0) < args.max_inflight_per_model

            def pop_next_ready_task(now_ts: float) -> dict[str, Any] | None:
                nonlocal round_robin_index
                if not model_order:
                    return None
                model_count = len(model_order)
                for offset in range(model_count):
                    idx = (round_robin_index + offset) % model_count
                    model = model_order[idx]
                    queue = pending_by_model.get(model)
                    if not queue:
                        continue
                    if not model_can_submit(model):
                        continue
                    if model_next_ready_at.get(model, 0.0) > now_ts:
                        continue
                    task = queue.popleft()
                    round_robin_index = (idx + 1) % model_count
                    return task
                return None

            def next_wake_time(now_ts: float) -> float:
                ready_times: list[float] = []
                for model in model_order:
                    queue = pending_by_model.get(model)
                    if not queue:
                        continue
                    if not model_can_submit(model):
                        continue
                    ready_times.append(max(model_next_ready_at.get(model, 0.0), now_ts))
                if not ready_times:
                    return now_ts + 0.1
                return min(ready_times)

            with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallelism) as pool:
                in_flight: dict[
                    concurrent.futures.Future[dict[str, Any]],
                    tuple[dict[str, Any], int],
                ] = {}

                def submit_collect_task(task: dict[str, Any]) -> None:
                    sample_id = sample_id_from_row(task, context="Collect task list")
                    next_attempt = task_attempts.get(sample_id, 0) + 1
                    task_attempts[sample_id] = next_attempt
                    model = str(task.get("model", ""))
                    model_in_flight[model] = model_in_flight.get(model, 0) + 1
                    future = pool.submit(
                        collect_one,
                        task,
                        client=client,
                        system_prompt=args.response_system_prompt,
                        omit_system_prompt=omit_system_prompt,
                        temperature=args.temperature,
                        max_tokens=args.max_tokens,
                        empty_response_retries=args.empty_response_retries,
                        retries=args.retries,
                        pause_seconds=args.pause_seconds,
                        dry_run=args.dry_run,
                        store_request_messages=bool(args.store_request_messages),
                        store_response_raw=bool(args.store_response_raw),
                        detection_config=detection_config,
                    )
                    in_flight[future] = (task, next_attempt)

                while completed < total:
                    while len(in_flight) < args.parallelism:
                        next_task = pop_next_ready_task(time.time())
                        if next_task is None:
                            break
                        submit_collect_task(next_task)

                    if not in_flight:
                        if pending_task_count() == 0:
                            break
                        now_ts = time.time()
                        wake_at = next_wake_time(now_ts)
                        sleep_seconds = max(0.05, min(wake_at - now_ts, 2.0))
                        time.sleep(sleep_seconds)
                        continue

                    done, _ = concurrent.futures.wait(
                        in_flight,
                        return_when=concurrent.futures.FIRST_COMPLETED,
                        timeout=1.0,
                    )
                    if not done:
                        continue

                    for future in done:
                        task, attempt = in_flight.pop(future)
                        attempt_count += 1
                        model = str(task.get("model", ""))
                        if model_in_flight.get(model, 0) > 0:
                            model_in_flight[model] -= 1

                        try:
                            record = future.result()
                        except Exception as exc:
                            prompt = task["prompt"]
                            record = {
                                "sample_id": task["sample_id"],
                                "run_index": task["run_index"],
                                "model": task["model"],
                                "model_id": task.get("model_id", task["model"]),
                                "model_org": task.get("model_org", "unknown"),
                                "model_name": task.get(
                                    "model_name", task.get("model_id", task["model"])
                                ),
                                "model_reasoning_level": task.get(
                                    "model_reasoning_level", "default"
                                ),
                                "model_row": task.get("model_row", task["model"]),
                                "response_reasoning_effort": task.get(
                                    "response_reasoning_effort"
                                ),
                                "prompt_id": prompt["id"],
                                "category": prompt["category"],
                                "surfaces": prompt["surfaces"],
                                "prompt_text": prompt["prompt"],
                                "prompt_description": prompt.get("description", ""),
                                "stateless_request": True,
                                "request_messages": [],
                                "response_text": "",
                                "response_id": "",
                                "response_usage": {},
                                "response_latency_ms": None,
                                "response_created": None,
                                "response_finish_reason": None,
                                "warnings": [],
                                "response_raw": None,
                                "started_at_utc": None,
                                "finished_at_utc": utc_now_iso(),
                                "error_kind": "runtime_error",
                                "error_http_status": None,
                                "error_retryable": None,
                                "error_retry_after_seconds": None,
                                "error": f"Worker failure: {exc}",
                                "detection": {},
                            }
                        enrich_collect_record_metrics(record)
                        record["collect_attempt"] = attempt

                        should_requeue_for_rate_limit = False
                        if args.rate_limit_requeue and record.get("error"):
                            if is_rate_limit_error_record(record):
                                if attempt < args.rate_limit_max_attempts:
                                    retry_after_seconds = _coerce_float(
                                        record.get("error_retry_after_seconds")
                                    )
                                    if (
                                        retry_after_seconds is not None
                                        and retry_after_seconds >= 0
                                    ):
                                        cooldown = retry_after_seconds
                                    else:
                                        cooldown = (
                                            args.rate_limit_cooldown_seconds
                                            * min(float(2 ** (attempt - 1)), 16.0)
                                        )
                                    cooldown = max(cooldown, 0.0)
                                    if args.rate_limit_cooldown_max_seconds > 0:
                                        cooldown = min(
                                            cooldown,
                                            args.rate_limit_cooldown_max_seconds,
                                        )
                                    if args.rate_limit_cooldown_jitter_seconds > 0:
                                        cooldown += random.uniform(
                                            0.0, args.rate_limit_cooldown_jitter_seconds
                                        )
                                    retry_at_epoch = time.time() + cooldown
                                    model_next_ready_at[model] = max(
                                        model_next_ready_at.get(model, 0.0),
                                        retry_at_epoch,
                                    )
                                    pending_by_model[model].append(task)
                                    should_requeue_for_rate_limit = True
                                    rate_limit_requeue_count += 1
                                    retry_at_iso = dt.datetime.fromtimestamp(
                                        retry_at_epoch, tz=dt.timezone.utc
                                    ).isoformat()
                                    events_writer.append(
                                        {
                                            "timestamp_utc": utc_now_iso(),
                                            "phase": "collect",
                                            "event": "task_rate_limit_requeue",
                                            "sample_id": record.get("sample_id"),
                                            "model": record.get("model"),
                                            "prompt_id": record.get("prompt_id"),
                                            "run_index": record.get("run_index"),
                                            "attempt": attempt,
                                            "retry_at_utc": retry_at_iso,
                                            "cooldown_seconds": round(cooldown, 3),
                                            "error": record.get("error", ""),
                                        }
                                    )
                                    print(
                                        f"[collect {completed}/{total}] requeue rate_limit "
                                        f"model={record.get('model')} prompt={record.get('prompt_id')} "
                                        f"run={record.get('run_index')} attempt={attempt} "
                                        f"cooldown={cooldown:.2f}s",
                                        flush=True,
                                    )
                                else:
                                    final_rate_limit_error_count += 1

                        if should_requeue_for_rate_limit:
                            continue

                        completed += 1
                        record["status"] = "error" if record.get("error") else "ok"
                        records.append(record)
                        partial_writer.append(record)
                        status = record["status"]
                        detection = record.get("detection", {})
                        classification = detection.get("classification", "")
                        stuck_indicator = (
                            " STUCK!" if classification == "stuck"
                            else " BORDERLINE" if classification == "borderline"
                            else ""
                        )
                        events_writer.append(
                            {
                                "timestamp_utc": utc_now_iso(),
                                "phase": "collect",
                                "event": "task_complete",
                                "status": status,
                                "sample_id": record.get("sample_id"),
                                "model": record.get("model"),
                                "prompt_id": record.get("prompt_id"),
                                "run_index": record.get("run_index"),
                                "attempt": attempt,
                                "detection_classification": detection.get("classification"),
                                "detection_stuck": detection.get("stuck"),
                                "error": record.get("error", ""),
                            }
                        )
                        error_suffix = (
                            f" error={record.get('error')}" if status == "error" else ""
                        )
                        print(
                            f"[collect {completed}/{total}] {status} "
                            f"model={record['model']} prompt={record['prompt_id']} run={record['run_index']} "
                            f"attempt={attempt}{stuck_indicator}{error_suffix}",
                            flush=True,
                        )

    validate_collect_integrity(tasks, records)

    records.sort(
        key=lambda row: (
            str(row.get("model", "")),
            str(row.get("response_reasoning_effort", "")),
            int(row.get("run_index", 0) or 0),
            str(row.get("prompt_id", "")),
        )
    )
    for row in records:
        enrich_collect_record_metrics(row)
    write_jsonl(final_responses_path, records)

    elapsed = round(time.perf_counter() - started, 3)

    # Compute detection summary
    stuck_count = sum(1 for row in records if row.get("detection", {}).get("classification") == "stuck")
    borderline_count = sum(1 for row in records if row.get("detection", {}).get("classification") == "borderline")
    not_stuck_count = sum(1 for row in records if row.get("detection", {}).get("classification") == "not_stuck")

    collection_stats = {
        "elapsed_seconds": elapsed,
        "total_records": len(records),
        "error_count": sum(1 for row in records if row.get("error")),
        "success_count": sum(1 for row in records if not row.get("error")),
        "stuck_count": stuck_count,
        "borderline_count": borderline_count,
        "not_stuck_count": not_stuck_count,
        "attempt_count": attempt_count,
        "max_attempt_observed": max(task_attempts.values(), default=0),
        "rate_limit_requeue_count": rate_limit_requeue_count,
        "final_rate_limit_error_count": final_rate_limit_error_count,
        "resumed": bool(args.resume),
        "checkpoint_rows_at_start": len(checkpoint_records),
        "new_rows_processed": len(tasks_to_run),
        "usage_summary": summarize_collect_usage(records),
    }
    write_json(run_dir / "collection_stats.json", collection_stats)
    write_collect_review_csv(run_dir / "responses_review.csv", records)

    print("", flush=True)
    print(f"Collection complete in {elapsed}s", flush=True)
    print(f"  Total: {len(records)} | Stuck: {stuck_count} | Borderline: {borderline_count} | Not Stuck: {not_stuck_count} | Errors: {collection_stats['error_count']}", flush=True)
    print(f"Artifacts: {run_dir}", flush=True)
    print(f"- {run_dir / 'collection_meta.json'}", flush=True)
    print(f"- {run_dir / 'prompts_snapshot.json'}", flush=True)
    print(f"- {run_dir / 'responses.jsonl'}", flush=True)
    print(f"- {partial_responses_path}", flush=True)
    print(f"- {run_dir / 'collection_stats.json'}", flush=True)
    print(f"- {run_dir / 'responses_review.csv'}", flush=True)
    print(f"- {collect_events_path}", flush=True)

    if collection_stats["error_count"] > 0 and args.fail_on_error:
        print(
            f"Collection finished with {collection_stats['error_count']} errors. "
            "Exiting non-zero due to --fail-on-error.",
            file=sys.stderr,
            flush=True,
        )
        return 2
    return 0


# =============================================================================
# CLI PARSING
# =============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="A-Trap Benchmark: Test if LLMs get stuck generating A's."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser(
        "collect",
        help="Collect model responses for benchmark prompts.",
    )
    collect.add_argument("--prompts", default="prompts.json")
    collect.add_argument("--models", default="")
    collect.add_argument("--models-file", default="")
    collect.add_argument("--config", default="config.json")
    collect.add_argument("--output-dir", default="runs")
    collect.add_argument(
        "--run-id",
        default="",
        help="Optional explicit run id. Default: UTC timestamp.",
    )
    collect.add_argument(
        "--num-runs",
        type=int,
        default=1,
        help="Number of independent repeats per model x prompt.",
    )
    collect.add_argument(
        "--parallelism",
        type=int,
        default=4,
        help="Concurrent OpenRouter calls during collection.",
    )
    collect.add_argument(
        "--max-inflight-per-model",
        type=int,
        default=0,
        help="Cap concurrent in-flight requests per model. 0 disables the cap.",
    )
    collect.add_argument("--limit", type=int, default=0)
    collect.add_argument("--categories", default="")
    collect.add_argument("--temperature", type=float, default=None)
    collect.add_argument("--max-tokens", type=int, default=0,
                         help="Max response tokens. 0 = no limit (omit from API call).")
    collect.add_argument(
        "--empty-response-retries",
        type=int,
        default=2,
        help="Additional retries when API returns an empty assistant content string.",
    )
    collect.add_argument("--pause-seconds", type=float, default=0.0)
    collect.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Max attempts per API call (bounded; default: 3).",
    )
    collect.add_argument("--timeout-seconds", type=int, default=120)
    collect.add_argument(
        "--response-system-prompt",
        default=DEFAULT_RESPONSE_SYSTEM_PROMPT,
    )
    collect.add_argument(
        "--omit-response-system-prompt",
        action="store_true",
        help="Omit system prompt entirely (send only the user message).",
    )
    collect.add_argument(
        "--response-reasoning-effort",
        choices=REASONING_EFFORT_CLI_CHOICES,
        default="off",
        help="Reasoning effort for response generation. Use off to omit reasoning settings.",
    )
    collect.add_argument(
        "--model-reasoning-efforts",
        default="",
        help="Optional JSON object mapping model id to reasoning effort(s).",
    )
    collect.add_argument(
        "--store-request-messages",
        action="store_true",
        help="Store request messages in responses.jsonl.",
    )
    collect.add_argument(
        "--store-response-raw",
        action="store_true",
        help="Store raw provider payload in responses.jsonl.",
    )
    collect.add_argument(
        "--shuffle-tasks",
        action="store_true",
        help="Randomize request order before execution.",
    )
    collect.add_argument("--seed", type=int, default=42)
    collect.add_argument(
        "--rate-limit-requeue",
        dest="rate_limit_requeue",
        action="store_true",
        default=True,
        help="Requeue 429/rate-limited tasks with model cooldown (default: enabled).",
    )
    collect.add_argument(
        "--no-rate-limit-requeue",
        dest="rate_limit_requeue",
        action="store_false",
        help="Disable model-aware rate-limit requeue behavior.",
    )
    collect.add_argument(
        "--rate-limit-cooldown-seconds",
        type=float,
        default=20.0,
        help="Base cooldown before retrying a rate-limited model.",
    )
    collect.add_argument(
        "--rate-limit-cooldown-max-seconds",
        type=float,
        default=300.0,
        help="Maximum cooldown cap for rate-limit retries.",
    )
    collect.add_argument(
        "--rate-limit-cooldown-jitter-seconds",
        type=float,
        default=1.0,
        help="Random jitter added to model cooldown.",
    )
    collect.add_argument(
        "--rate-limit-max-attempts",
        type=int,
        default=12,
        help="Max total attempts per sample_id before surfacing a final rate-limit error.",
    )
    collect.add_argument(
        "--checkpoint-fsync-every",
        type=int,
        default=20,
        help="Force fsync on partial progress logs every N finalized rows.",
    )
    collect.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip API calls and write deterministic placeholders.",
    )
    collect.add_argument(
        "--resume",
        action="store_true",
        help="Resume an existing run directory (requires --run-id).",
    )
    collect.add_argument(
        "--fail-on-error",
        action="store_true",
        default=True,
        help="Exit non-zero if any collection errors occur.",
    )
    collect.add_argument(
        "--no-fail-on-error",
        dest="fail_on_error",
        action="store_false",
        help="Exit zero even if collection errors occur.",
    )

    return parser.parse_args()


# =============================================================================
# MAIN
# =============================================================================

def main() -> int:
    # Load .env file from project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(script_dir)
    load_dotenv(os.path.join(base_dir, ".env"))

    args = parse_args()
    if args.command == "collect":
        return run_collect(args)
    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
