#!/usr/bin/env python3
"""A-Trap Benchmark: Test if LLMs get stuck generating A's.

Minimal version for hello-world testing.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from dotenv import load_dotenv


# =============================================================================
# DETECTION HEURISTICS
# =============================================================================

def detect_a_trap(response: str, finish_reason: str | None = None) -> dict[str, Any]:
    """Analyze response for A-trap indicators."""
    total_chars = len(response)
    a_count = response.lower().count('a')
    a_ratio = a_count / max(total_chars, 1)

    # Find longest consecutive A run
    runs = re.findall(r'a+', response.lower())
    longest_run = max((len(r) for r in runs), default=0)

    # Detection rules
    stuck = (
        a_ratio > 0.5 or                                    # >50% A's
        longest_run > 100 or                                # 100+ consecutive A's
        (finish_reason == "length" and a_count > 500)       # Cut off while A-ing
    )

    return {
        "stuck": stuck,
        "a_count": a_count,
        "a_ratio": round(a_ratio, 4),
        "longest_a_run": longest_run,
        "total_chars": total_chars,
    }


# =============================================================================
# OPENROUTER CLIENT
# =============================================================================

class OpenRouterAPIError(RuntimeError):
    """Custom error for OpenRouter API failures."""
    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class OpenRouterClient:
    """Simple OpenRouter API client."""

    def __init__(self, api_key: str, timeout_seconds: int = 120) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.app_name = "a-trap-benchmark"

    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Send a chat completion request."""
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens > 0:
            payload["max_tokens"] = max_tokens

        encoded = json.dumps(payload).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": self.app_name,
        }

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
            raise OpenRouterAPIError(
                f"HTTP {exc.code} from OpenRouter: {detail}",
                status_code=exc.code,
                retryable=exc.code in (429, 500, 502, 503, 504),
            ) from exc


def extract_response_text(api_response: dict[str, Any]) -> str:
    """Extract text content from API response."""
    if api_response.get("error"):
        err = api_response.get("error")
        raise RuntimeError(f"API returned error: {json.dumps(err)}")

    choices = api_response.get("choices", [])
    if not choices:
        return ""

    message = choices[0].get("message", {})
    content = message.get("content", "")

    # Handle list content (some models return structured content)
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)

    return str(content) if content else ""


def extract_finish_reason(api_response: dict[str, Any]) -> str | None:
    """Extract finish reason from API response."""
    choices = api_response.get("choices", [])
    if not choices:
        return None
    return choices[0].get("finish_reason")


def extract_usage(api_response: dict[str, Any]) -> dict[str, Any]:
    """Extract token usage from API response."""
    return api_response.get("usage", {})


# =============================================================================
# PROMPT LOADING
# =============================================================================

def load_prompts(path: str) -> list[dict[str, Any]]:
    """Load prompts from JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    prompts = []
    for category in data.get("categories", []):
        cat_name = category.get("category", "unknown")
        for prompt in category.get("prompts", []):
            prompt["category"] = cat_name
            prompts.append(prompt)

    return prompts


def load_config(path: str) -> dict[str, Any]:
    """Load config from JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def run_single(
    model: str,
    prompt: dict[str, Any],
    client: OpenRouterClient,
    max_tokens: int = 4096,
    temperature: float | None = None,
) -> dict[str, Any]:
    """Run a single prompt against a single model."""

    messages = [{"role": "user", "content": prompt["prompt"]}]

    started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    t0 = time.perf_counter()

    result = {
        "model": model,
        "prompt_id": prompt["id"],
        "prompt_category": prompt.get("category", "unknown"),
        "prompt_text": prompt["prompt"][:200] + "..." if len(prompt["prompt"]) > 200 else prompt["prompt"],
        "response_text": "",
        "finish_reason": None,
        "usage": {},
        "detection": {},
        "error": "",
        "latency_ms": 0,
        "started_at": started_at,
    }

    try:
        response = client.chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        result["response_text"] = extract_response_text(response)
        result["finish_reason"] = extract_finish_reason(response)
        result["usage"] = extract_usage(response)
        result["detection"] = detect_a_trap(result["response_text"], result["finish_reason"])

    except Exception as exc:
        result["error"] = str(exc)
        result["detection"] = {"stuck": False, "error": True}

    result["latency_ms"] = int((time.perf_counter() - t0) * 1000)
    result["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()

    return result


def main() -> int:
    # Load .env file from project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(script_dir)
    load_dotenv(os.path.join(base_dir, ".env"))

    parser = argparse.ArgumentParser(description="A-Trap Benchmark")
    parser.add_argument("--config", default="config.json", help="Config file path")
    parser.add_argument("--model", help="Override model (use first from config if not specified)")
    parser.add_argument("--prompt-id", help="Run specific prompt ID only")
    parser.add_argument("--prompt-index", type=int, default=0, help="Run prompt at index (default: 0)")
    parser.add_argument("--max-tokens", type=int, default=4096, help="Max tokens for response")
    parser.add_argument("--dry-run", action="store_true", help="Print what would run without calling API")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Load config
    config_path = args.config
    if not os.path.isabs(config_path):
        config_path = os.path.join(base_dir, config_path)

    config = load_config(config_path)

    # Load prompts
    prompts_file = config.get("collect", {}).get("prompts_file", "prompts.json")
    if not os.path.isabs(prompts_file):
        prompts_file = os.path.join(base_dir, prompts_file)

    prompts = load_prompts(prompts_file)

    if not prompts:
        print("ERROR: No prompts loaded")
        return 1

    # Select prompt
    if args.prompt_id:
        prompt = next((p for p in prompts if p["id"] == args.prompt_id), None)
        if not prompt:
            print(f"ERROR: Prompt ID '{args.prompt_id}' not found")
            print(f"Available IDs: {[p['id'] for p in prompts]}")
            return 1
    else:
        if args.prompt_index >= len(prompts):
            print(f"ERROR: Prompt index {args.prompt_index} out of range (max: {len(prompts) - 1})")
            return 1
        prompt = prompts[args.prompt_index]

    # Select model
    models = config.get("collect", {}).get("models", [])
    model = args.model or (models[0] if models else None)

    if not model:
        print("ERROR: No model specified and none in config")
        return 1

    # Get API key
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: OPENROUTER_API_KEY environment variable not set")
        return 1

    print("=" * 60)
    print("A-TRAP BENCHMARK - Hello World")
    print("=" * 60)
    print(f"Model:    {model}")
    print(f"Prompt:   {prompt['id']} ({prompt.get('category', 'unknown')})")
    print(f"Max Tokens: {args.max_tokens}")
    print("-" * 60)

    if args.verbose:
        print(f"Prompt text:\n{prompt['prompt'][:500]}{'...' if len(prompt['prompt']) > 500 else ''}")
        print("-" * 60)

    if args.dry_run:
        print("[DRY RUN] Would call API with above parameters")
        return 0

    # Run it
    client = OpenRouterClient(api_key)

    print("Calling API...")
    result = run_single(
        model=model,
        prompt=prompt,
        client=client,
        max_tokens=args.max_tokens,
    )

    print("-" * 60)
    print("RESULT:")
    print("-" * 60)

    if result["error"]:
        print(f"ERROR: {result['error']}")
    else:
        response_preview = result["response_text"][:500]
        if len(result["response_text"]) > 500:
            response_preview += f"... [{len(result['response_text'])} chars total]"

        print(f"Response:\n{response_preview}")
        print("-" * 60)
        print(f"Finish Reason: {result['finish_reason']}")
        print(f"Latency: {result['latency_ms']}ms")
        print(f"Usage: {result['usage']}")
        print("-" * 60)
        print("DETECTION:")
        detection = result["detection"]
        print(f"  Stuck:          {detection['stuck']}")
        print(f"  A Count:        {detection['a_count']}")
        print(f"  A Ratio:        {detection['a_ratio']:.2%}")
        print(f"  Longest A Run:  {detection['longest_a_run']}")
        print(f"  Total Chars:    {detection['total_chars']}")

    print("=" * 60)

    # Output JSON for piping
    if args.verbose:
        print("\nFull JSON result:")
        print(json.dumps(result, indent=2, default=str))

    return 0 if not result["error"] else 1


if __name__ == "__main__":
    sys.exit(main())
