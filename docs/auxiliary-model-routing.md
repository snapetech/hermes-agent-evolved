# Auxiliary Model Routing

Hermes uses auxiliary models for work that is not the main chat turn:
compression, web extraction, session search, vision, approvals, MCP reasoning,
memory flushing, session titles, and skills hub lookups. The goal is to spend
the cheapest reliable tokens for each job without letting weak background
models corrupt state.

## Current Workstation Profile

The active default profile at setup time had these usable routes:

| Lane | Provider | Model | Notes |
| --- | --- | --- | --- |
| Local | `custom` | `gemma4-26b-a4b-it:q4km` | llama.cpp-compatible endpoint at `http://10.0.0.10:8001/v1`; configured context `65,536`; selected from local Hermes quality scores, not community benchmarks. |
| Kilo free | `kilocode` | `kilo-auto/free` | Free/high-volume lane from `KILOCODE_API_KEY`; good for disposable summaries and labels. |
| Codex | `openai-codex` | `gpt-5.2-codex` | OAuth-backed, abundant in this stack, supports the Responses adapter and vision. |
| Claude | `anthropic` | `claude-haiku-4-5-20251001` | Available through Claude Code/OAuth, but limited and expensive; reserved as a last fallback, not a primary route. |

Do not copy this matrix blindly to another machine. Run `hermes model` and
`Configure auxiliary models...` or inspect `~/.hermes/config.yaml` for the
profile that is actually active.

## Active Routing

The profile was tuned as follows:

| Task | Route | Why |
| --- | --- | --- |
| `compression` | local Gemma | Compression is state-critical and can be large. Local Gemma is free, private, and is now the highest-scoring local workhorse in our Hermes suite. |
| `web_extract` | Kilo free | High-volume summarization where occasional weak output can be retried or escalated. |
| `session_search` | Kilo free | Cheap recall summarization; exact session records remain in SQLite. |
| `title_generation` | Kilo free | Disposable, low-risk labels. |
| `skills_hub` | Kilo free | Cheap catalog/search assistance. |
| `vision` | Codex | The local Qwen endpoint is text-only; Codex supports image payloads through the Responses adapter. |
| `approval` | Codex | Approval mistakes can execute or block commands. Use a stronger conservative model. |
| `mcp` | Codex | MCP tool selection often needs reasoning over schemas and arguments. |
| `flush_memories` | Codex | Memory writes become durable user state; do not entrust this to the weakest free route. |

## Subagent Delegation

Subagents are not auxiliary calls. `delegate_task` creates full child
`AIAgent` instances with their own session, context compressor, terminal state,
tool cache, and provider runtime. That is the right architecture: a subagent is
not a quick summarizer, it is a working agent that may call tools for many turns.

The active delegation profile now favors the always-on single-card local model
by default:

```yaml
delegation:
  max_concurrent_children: 1
  max_iterations: 50
  llm_mode: single
  llm_mode_command:
    - /home/example-user/bin/hermes-llm-mode
  llm_mode_timeout: 240
  llm_mode_fallback_to_single: true
  restore_llm_mode: single
```

Because `delegation.provider` is blank, child agents inherit the parent runtime
instead of using the `auxiliary.*` matrix. In this profile, that means local
Gemma direct unless the parent has switched models. `single` maps to the
7900 XT-only Gemma4 26B-A4B Q4_K_M service. Qwen split-card modes are now
experimental only: they touch the 9070 XT display GPU and currently have
throughput-only rows, not Hermes quality scores.

The Kubernetes gateway also runs the local endpoint through an admission proxy
with `--max-input-tokens 42000`. That guard is lower than the advertised 64K
slot on purpose: the single-card 7900 XT path has OOMed during prefill on
requests around 54K prompt tokens. The live proxy rejects oversized requests
instead of summarizing them itself; Hermes owns transcript compaction and retry.
Use dual-card modes only when the quality or memory tradeoff is worth the lower
throughput.

That gives cheap local subagents first, while still preserving higher-quality
lanes for applicable work:

- Default: `single` for simple code exploration, shell/file work, scoped fixes,
  and most read-only investigation.
- Escalate to `dual-q5` only for substantial coding, review, planning, or
  synthesis where the quality gain beats the throughput hit.
- Escalate to `dual-q6` only when quality matters more than latency.
- Use Codex when parallel child agents are more valuable than local GPU time.
- Use Kilo free only for bounded, read-only, low-risk delegated work.
- Use Manifest only after its chat-completions path returns non-empty responses.

This setup does not use Kilo/Codex/Manifest as the default child-agent lane.
That is deliberate for now:

- Kilo free is good for small summaries, but too weak to be the default for
  autonomous tool-using child agents.
- Codex is reliable and abundant, but it is better reserved for child-agent
  escalation or a future `delegation.provider: openai-codex` profile.
- Manifest resolves as a provider in this profile, but a smoke test returned
  `/v1/models` as `404` and a tiny `manifest/auto` chat completion returned an
  empty assistant message. Do not make Manifest the default delegation provider
  until that endpoint returns meaningful completions.

Named route notes are stored in the live config under `delegation.routes`:

```yaml
delegation:
  routes:
    local-single:
      provider: custom
      model: qwen3.6-35b-a3b:iq4xs
      base_url: http://10.0.0.10:8001/v1
      llm_mode: single
      max_concurrent_children: 1
    local-quality:
      provider: custom
      model: qwen3.6-35b-a3b:iq4xs
      base_url: http://10.0.0.10:8001/v1
      llm_mode: dual-q5
      max_concurrent_children: 1
    local-stretch:
      provider: custom
      model: qwen3.6-35b-a3b:iq4xs
      base_url: http://10.0.0.10:8001/v1
      llm_mode: dual-q6
      max_concurrent_children: 1
    codex-parallel:
      provider: openai-codex
      model: gpt-5.2-codex
      llm_mode: ""
      max_concurrent_children: 3
    kilo-cheap:
      provider: kilocode
      model: kilo-auto/free
      llm_mode: ""
      max_concurrent_children: 3
    manifest-router:
      provider: manifest
      model: manifest/auto
      llm_mode: ""
      max_concurrent_children: 3
      enabled: false
```

The current `delegate_task` implementation does not yet consume
`delegation.routes` as first-class named routes. For now they are executable
policy notes and ready config blocks. The direct controls that are active today
are still `delegation.provider`, `delegation.model`, `delegation.llm_mode`, and
per-call/per-task `llm_mode`.

Use this override when Manifest is healthy and you want child-agent traffic in
the router/cost dashboard:

```yaml
delegation:
  provider: manifest
  model: manifest/auto
  max_concurrent_children: 3
  llm_mode: ""
```

Use this override when subagents should spend Codex subscription capacity
instead of local GPU time:

```yaml
delegation:
  provider: openai-codex
  model: gpt-5.2-codex
  max_concurrent_children: 3
  llm_mode: ""
```

Use this override only for cheap, bounded, read-only delegation where failure is
acceptable:

```yaml
delegation:
  provider: kilocode
  model: kilo-auto/free
  max_concurrent_children: 3
  llm_mode: ""
```

Do not increase `max_concurrent_children` above `1` for local direct Qwen unless
the local server is known to handle concurrent long-running agents. Parallel
subagents against one local model can be slower than serial execution and can
make compaction timing noisier.

The Kilo paid and Claude routes are retained as fallbacks, but not first choice:

```yaml
adaptive_fallback_routing:
  enabled: true
  free_first: true
  dynamic_kilo_catalog: true
  free_candidates:
    - provider: kilocode
      model: kilo-auto/free
  paid_candidates:
    - provider: openai-codex
      model: gpt-5.2-codex
    - provider: kilocode
      model: moonshotai/kimi-k2.6
    - provider: anthropic
      model: claude-haiku-4-5-20251001
```

## Config Snapshot

The effective auxiliary section is:

```yaml
auxiliary:
  compression:
    provider: custom
    model: qwen3.6-35b-a3b:iq4xs
    base_url: http://10.0.0.10:8001/v1
    api_key: ""
    timeout: 180
    context_length: 65536

  web_extract:
    provider: kilocode
    model: kilo-auto/free
    timeout: 240

  session_search:
    provider: kilocode
    model: kilo-auto/free
    timeout: 45

  title_generation:
    provider: kilocode
    model: kilo-auto/free
    timeout: 20

  skills_hub:
    provider: kilocode
    model: kilo-auto/free
    timeout: 45

  vision:
    provider: openai-codex
    model: gpt-5.2-codex
    timeout: 120
    download_timeout: 30

  approval:
    provider: openai-codex
    model: gpt-5.2-codex
    timeout: 45

  mcp:
    provider: openai-codex
    model: gpt-5.2-codex
    timeout: 90

  flush_memories:
    provider: openai-codex
    model: gpt-5.2-codex
    timeout: 120
```

Blank `api_key` on local custom endpoints is intentional. Hermes falls back to
`OPENAI_API_KEY`, and then to `no-key-required` for local OpenAI-compatible
servers.

## Compaction Timing Knobs

The profile uses:

```yaml
compression:
  enabled: true
  threshold: 0.42
  target_ratio: 0.18
  protect_last_n: 12
  artifacts_enabled: true
  soft_static_fallback: false
  forced_static_fallback: true
```

Rationale:

- `threshold: 0.42` delays compaction compared with the old `0.25`, reducing
  churn and latency, while still leaving about 38k tokens of headroom on the
  configured 65k context.
- `target_ratio: 0.18` keeps the live recent tail compact after summarization
  so the next tool burst has room.
- `protect_last_n: 12` keeps enough immediate exchange context without forcing
  a huge tail when tool calls produce many messages.
- `artifacts_enabled: true` stores exact compacted spans. The live prompt is
  lossy; the artifact archive is the source of truth.
- `soft_static_fallback: false` means soft/preflight compaction skips if the
  summary model fails. That avoids preventable live-context loss.
- `forced_static_fallback: true` means provider overflow can still shrink the
  prompt using the deterministic checkpoint when no LLM summary is available.

## Operating Rules

Use local Gemma when the task is text-only, privacy-sensitive, and its input fits
comfortably under the local context. Compression matches that profile.

Use Kilo free when outputs are cheap to retry or low-risk: titles, search
snippets, catalog help, and web extraction drafts. Kilo free should not be the
only guard on command execution or memory state.

Use Codex when the task needs stronger judgment, tool discipline, multimodal
support, or durable-state accuracy: approvals, MCP, memory flushing, and vision.

Use Claude only when a human intentionally escalates, or as the last configured
fallback. It is excellent, but this stack treats it as limited and expensive.

## Verification

After changing this file or `~/.hermes/config.yaml`, verify routing without
printing credentials:

```bash
source .venv/bin/activate
python - <<'PY'
from pathlib import Path
from hermes_cli.env_loader import load_hermes_dotenv
from hermes_constants import get_hermes_home
load_hermes_dotenv(hermes_home=get_hermes_home(), project_env=Path.cwd()/'.env')

from agent.auxiliary_client import get_text_auxiliary_client, resolve_vision_provider_client

for task in (
    "compression", "web_extract", "session_search", "approval", "mcp",
    "flush_memories", "title_generation", "skills_hub",
):
    client, model = get_text_auxiliary_client(task)
    print(task, bool(client), model, type(client).__name__ if client else None)

provider, client, model = resolve_vision_provider_client("openai-codex", "gpt-5.2-codex")
print("vision", provider, bool(client), model, type(client).__name__ if client else None)
PY
```

Expected for this profile: every line resolves, Kilo tasks use `OpenAI`,
Codex tasks use `CodexAuxiliaryClient`, and compression uses the local
OpenAI-compatible client.

Verify delegation routing separately because it is not an auxiliary call:

```bash
source .venv/bin/activate
python - <<'PY'
from pathlib import Path
from hermes_cli.env_loader import load_hermes_dotenv
from hermes_constants import get_hermes_home
load_hermes_dotenv(hermes_home=get_hermes_home(), project_env=Path.cwd()/'.env')

import yaml
from tools.delegate_tool import _resolve_delegation_credentials

cfg = yaml.safe_load((get_hermes_home() / "config.yaml").read_text()) or {}
print(cfg.get("delegation", {}))
print(_resolve_delegation_credentials(cfg.get("delegation", {}), parent_agent=None))
PY
```

When `delegation.provider` is blank, the resolved credentials intentionally
show `None` values because the child inherits the parent runtime.

## Failure Modes

If Kilo returns empty output, the auxiliary client can escalate low-quality
successes to stronger routes. Keep the Kilo lane on low-risk tasks so this
does not turn normal operation into paid routing.

If local Qwen is down, compression cannot use the configured primary route.
Soft compaction will skip; forced compaction can use extractive fallback during
overflow. If local downtime is frequent, temporarily route compression to
`openai-codex/gpt-5.2-codex`.

If compaction happens too often, raise `compression.threshold` toward `0.50`.
If provider overflow appears before compaction, lower it toward `0.35`.

If summaries miss important details, keep the current compaction artifact tools
enabled and either improve the local model, raise the compression timeout, or
route `auxiliary.compression` to Codex.
