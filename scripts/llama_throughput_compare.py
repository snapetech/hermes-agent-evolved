#!/usr/bin/env python3
"""Measure llama.cpp OpenAI-compatible endpoint throughput.

This uses llama.cpp's response `timings` object when available. It is intended
for practical local comparisons, not benchmark leaderboard claims.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
from pathlib import Path
from typing import Any


PROMPT = (
    "You are benchmarking local Hermes model throughput. "
    "Write a compact operational checklist for diagnosing a degraded agent "
    "gateway, including logs, model endpoint health, filesystem access, MCP "
    "availability, and a final operator summary. Keep the answer concrete."
)


def _request(base_url: str, model: str, max_tokens: int, timeout: int) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "stream": False,
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    started = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    body["wall_seconds"] = time.time() - started
    return body


def _num(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


def _tokens(body: dict[str, Any], section: str, fallback: str) -> int:
    timings = body.get("timings") or {}
    usage = body.get("usage") or {}
    value = timings.get(section)
    if isinstance(value, int):
        return value
    return int(usage.get(fallback) or 0)


def measure(base_url: str, model: str, repetitions: int, max_tokens: int, timeout: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for index in range(1, repetitions + 1):
        body = _request(base_url, model, max_tokens, timeout)
        timings = body.get("timings") or {}
        rows.append(
            {
                "run": index,
                "prompt_tokens": _tokens(body, "prompt_n", "prompt_tokens"),
                "completion_tokens": _tokens(body, "predicted_n", "completion_tokens"),
                "prompt_tokens_per_second": _num(timings.get("prompt_per_second")),
                "completion_tokens_per_second": _num(timings.get("predicted_per_second")),
                "wall_seconds": round(float(body.get("wall_seconds") or 0.0), 3),
                "finish_reason": ((body.get("choices") or [{}])[0] or {}).get("finish_reason"),
            }
        )

    def median(key: str) -> float | None:
        values = [row[key] for row in rows if isinstance(row.get(key), int | float)]
        if not values:
            return None
        return round(float(statistics.median(values)), 2)

    return {
        "model": model,
        "base_url": base_url,
        "repetitions": repetitions,
        "max_tokens": max_tokens,
        "median_prompt_tokens_per_second": median("prompt_tokens_per_second"),
        "median_completion_tokens_per_second": median("completion_tokens_per_second"),
        "median_wall_seconds": median("wall_seconds"),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=160)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    result = measure(args.base_url, args.model, args.repetitions, args.max_tokens, args.timeout)
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
