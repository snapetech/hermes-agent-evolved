#!/usr/bin/env python3
"""Probe llama.cpp endpoint behavior at varying context fill levels.

Two probe modes:
- needle: insert a unique fact at a known position in a long filler prompt and
  ask the model to retrieve it. Captures retrieval correctness alongside
  prompt-eval / generation throughput.
- synthesis: insert three facts at distinct positions and ask the model to
  combine them. Catches different long-ctx failure modes than needle.

Output is a single JSON document with one row per (mode, target_fill) cell
suitable for downstream tabulation.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


# Filler corpus: a deterministic mix of operational/technical sentences. The
# goal is plausible English without accidentally containing the needle facts.
FILLER_SENTENCES = [
    "The deployment script verifies that all systemd units are healthy before swapping the active model.",
    "Operators routinely rotate the gateway certificates on a quarterly basis to preserve compliance.",
    "Logs from the model endpoint include prompt tokens, completion tokens, and median latencies per request.",
    "Filesystem access is mediated through a sandboxed plugin layer that enforces path allowlists.",
    "MCP availability is monitored separately from the chat-completions endpoint to surface partial outages.",
    "The trajectory compressor reduces tool-call history to a digest that fits within a smaller working budget.",
    "Cron jobs export aggregate metrics to the observability bucket every fifteen minutes.",
    "Each plugin declares an isolation profile that pins capabilities to the minimum required surface.",
    "The benchmark harness pins decode temperature to zero so logic tasks stay deterministic across runs.",
    "Skill packs are loaded lazily based on the toolset distribution requested by the active scenario.",
    "Edge watchers stream display events into the gateway, where they fan out to subscribed agents.",
    "The retry utility applies exponential backoff with jitter for transient HTTP failures.",
    "Workspaces under benchmark_runs/ retain the per-cell artifacts that scorecards aggregate.",
    "The desktop bridge translates accessibility events into structured tool inputs for the agent loop.",
    "Hermes ships with a constraints file that pins termux-only dependencies to a narrow band.",
    "The fork policy specifies that hermes-agent-private is the canonical sync target, never NousResearch upstream.",
    "Discord relay messages annotate the originating channel and a stable thread identifier.",
    "Resource review jobs check gateway memory, CPU pressure, and any dangling subprocess descriptors.",
    "The introspection scan walks the loaded toolset graph to find unreachable or shadowed entries.",
    "Tinker training mixes generated trajectories with curated datasets at a configurable ratio.",
]


NEEDLE_FACT_TEMPLATES = [
    ("The secret operator codeword is {token}.", "operator codeword"),
    ("The maintenance window opens at exactly {token} hours UTC.", "maintenance window time"),
    ("The fallback gateway port is {token}.", "fallback gateway port"),
    ("The override config key resolves to {token}.", "override config key"),
    ("The audit trail signature for this run is {token}.", "audit trail signature"),
]


SYNTHESIS_FACTS = [
    ("incident reference number", "INC-{token}"),
    ("oncall rotation handle", "@rotation-{token}"),
    ("hotfix branch", "hotfix/{token}"),
]


def _make_token(rng: random.Random, length: int = 6) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(rng.choice(alphabet) for _ in range(length))


def _build_filler(rng: random.Random, target_chars: int) -> list[str]:
    """Build a filler text block with numbered prefix sentences."""
    out: list[str] = []
    chars = 0
    counter = 1
    while chars < target_chars:
        sentence = rng.choice(FILLER_SENTENCES)
        line = f"[{counter:05d}] {sentence}"
        out.append(line)
        chars += len(line) + 1
        counter += 1
    return out


def build_needle_prompt(
    rng: random.Random,
    target_chars: int,
    position: float,
) -> tuple[str, str, str]:
    """Return (prompt, expected_answer, label) for a needle probe."""
    template, label = NEEDLE_FACT_TEMPLATES[0]
    token = _make_token(rng)
    needle = template.format(token=token)

    filler = _build_filler(rng, target_chars)
    insert_at = max(0, min(len(filler) - 1, int(len(filler) * position)))
    filler.insert(insert_at, f"[NEEDLE] {needle}")

    body = "\n".join(filler)
    instruction = (
        "You will be shown a long log. Read it carefully. At the end you must "
        f"answer one question. The question is: what is the {label}?\n"
        "Answer with ONLY the exact value, no extra words."
    )
    prompt = f"{instruction}\n\n--- BEGIN LOG ---\n{body}\n--- END LOG ---\n\n"
    prompt += f"Question: What is the {label}? Reply with the exact value only."
    return prompt, token, "needle"


def build_synthesis_prompt(
    rng: random.Random,
    target_chars: int,
) -> tuple[str, dict[str, str], str]:
    """Return (prompt, expected_answers, label) for a synthesis probe.

    Inserts three distinct facts at quartile positions and asks the model to
    combine them into a single structured answer.
    """
    tokens = {label: _make_token(rng) for label, _ in SYNTHESIS_FACTS}
    expected: dict[str, str] = {}
    sentences: list[str] = []
    for (label, template), positional in zip(SYNTHESIS_FACTS, (0.2, 0.55, 0.85)):
        value = template.format(token=tokens[label])
        expected[label] = value
        sentences.append((positional, label, f"[FACT:{label}] {label} is {value}."))

    filler = _build_filler(rng, target_chars)
    for positional, _, sentence in sentences:
        idx = max(0, min(len(filler) - 1, int(len(filler) * positional)))
        filler.insert(idx, sentence)

    body = "\n".join(filler)
    field_list = ", ".join(label for label, _ in SYNTHESIS_FACTS)
    instruction = (
        "You will be shown a long log containing several embedded facts. "
        f"Extract the following fields and report them: {field_list}.\n"
        "Reply in the form 'field: value' on separate lines, exact values only, "
        "no extra commentary."
    )
    prompt = f"{instruction}\n\n--- BEGIN LOG ---\n{body}\n--- END LOG ---\n\n"
    prompt += "Extract the values now."
    return prompt, expected, "synthesis"


def _post(base_url: str, model: str, prompt: str, max_tokens: int, timeout: int) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=data,
        headers={"Content-Type": "application/json", "Authorization": "Bearer local"},
    )
    started = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    body["wall_seconds"] = time.time() - started
    return body


def _grade_needle(reply: str, expected: str) -> bool:
    return expected in reply


def _grade_synthesis(reply: str, expected: dict[str, str]) -> dict[str, bool]:
    return {label: value in reply for label, value in expected.items()}


def _num(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


def _content(body: dict[str, Any]) -> str:
    choices = body.get("choices") or []
    if not choices:
        return ""
    msg = (choices[0] or {}).get("message") or {}
    return msg.get("content") or ""


def run_cell(
    base_url: str,
    model: str,
    mode: str,
    target_chars: int,
    max_tokens: int,
    timeout: int,
    seed: int,
    position: float,
) -> dict[str, Any]:
    rng = random.Random(seed)
    if mode == "needle":
        prompt, expected, _ = build_needle_prompt(rng, target_chars, position)
    elif mode == "synthesis":
        prompt, expected, _ = build_synthesis_prompt(rng, target_chars)
    else:
        raise ValueError(f"unknown mode: {mode}")

    started = time.time()
    error: str | None = None
    body: dict[str, Any] | None = None
    try:
        body = _post(base_url, model, prompt, max_tokens, timeout)
    except urllib.error.HTTPError as exc:
        try:
            payload = exc.read().decode("utf-8", errors="replace")
        except Exception:
            payload = ""
        error = f"HTTP {exc.code}: {payload[:300]}"
    except Exception as exc:  # noqa: BLE001 - best effort probe
        error = f"{type(exc).__name__}: {exc}"

    elapsed = time.time() - started
    row: dict[str, Any] = {
        "mode": mode,
        "target_chars": target_chars,
        "wall_seconds": round(elapsed, 3),
        "error": error,
    }

    if body is None:
        row.update(
            {
                "prompt_tokens": None,
                "completion_tokens": None,
                "prompt_tokens_per_second": None,
                "completion_tokens_per_second": None,
                "finish_reason": None,
                "correct": False,
                "reply_excerpt": "",
            }
        )
        if mode == "synthesis":
            row["per_field_correct"] = {label: False for label, _ in SYNTHESIS_FACTS}
        return row

    timings = body.get("timings") or {}
    usage = body.get("usage") or {}
    reply = _content(body).strip()

    if mode == "needle":
        correct = _grade_needle(reply, expected)
        per_field = None
    else:
        per_field = _grade_synthesis(reply, expected)
        correct = all(per_field.values())

    prompt_tokens = timings.get("prompt_n") or usage.get("prompt_tokens") or 0
    completion_tokens = timings.get("predicted_n") or usage.get("completion_tokens") or 0

    row.update(
        {
            "prompt_tokens": int(prompt_tokens or 0),
            "completion_tokens": int(completion_tokens or 0),
            "prompt_tokens_per_second": _num(timings.get("prompt_per_second")),
            "completion_tokens_per_second": _num(timings.get("predicted_per_second")),
            "finish_reason": ((body.get("choices") or [{}])[0] or {}).get("finish_reason"),
            "correct": bool(correct),
            "reply_excerpt": reply[:240],
        }
    )
    if per_field is not None:
        row["per_field_correct"] = per_field
    return row


def parse_fill_levels(spec: str) -> list[int]:
    """Parse a comma-separated list of fill targets in characters.

    Each entry is either a raw number of characters (e.g. '50000') or a
    suffixed value like '32k', '64k' interpreted as characters * 1024.
    """
    out: list[int] = []
    for raw in spec.split(","):
        raw = raw.strip().lower()
        if not raw:
            continue
        if raw.endswith("k"):
            out.append(int(float(raw[:-1]) * 1024))
        else:
            out.append(int(raw))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--fill-levels",
        default="8k,32k,60k",
        help="Comma list of target prompt sizes in characters (suffix 'k' = *1024)",
    )
    parser.add_argument(
        "--modes",
        default="needle,synthesis",
        help="Comma list of probe modes to run",
    )
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--seed", type=int, default=20260428)
    parser.add_argument(
        "--needle-position",
        type=float,
        default=0.5,
        help="Fractional position of the needle within filler (0=start, 1=end)",
    )
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    fill_levels = parse_fill_levels(args.fill_levels)
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    rows: list[dict[str, Any]] = []
    for mode in modes:
        for target in fill_levels:
            row = run_cell(
                args.base_url,
                args.model,
                mode,
                target,
                args.max_tokens,
                args.timeout,
                args.seed,
                args.needle_position,
            )
            row["model"] = args.model
            rows.append(row)
            print(
                f"{mode:9s} fill={target:>8d} "
                f"prompt_tok={row.get('prompt_tokens')} "
                f"prompt_tps={row.get('prompt_tokens_per_second')} "
                f"completion_tps={row.get('completion_tokens_per_second')} "
                f"correct={row.get('correct')} "
                f"err={row.get('error') or '-'}",
                flush=True,
            )

    summary = {
        "model": args.model,
        "base_url": args.base_url,
        "rows": rows,
    }
    if rows:
        completion_tps = [
            r["completion_tokens_per_second"]
            for r in rows
            if isinstance(r.get("completion_tokens_per_second"), (int, float))
        ]
        if completion_tps:
            summary["median_completion_tps"] = round(
                float(statistics.median(completion_tps)), 2
            )

    text = json.dumps(summary, indent=2) + "\n"
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
