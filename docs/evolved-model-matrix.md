# Evolved Model And Hardware Matrix

The evolved deployment needs an OpenAI-compatible chat completions endpoint.
That endpoint can be local, host-side, in-cluster, or a remote API. The
Kubernetes gateway should not care as long as the endpoint is reachable from
the pod and the configured context length matches what the backend really
serves.

## Supported Endpoint Shapes

| Shape | Use When | Requirements | Admission Proxy |
| --- | --- | --- | --- |
| External API | You want the fastest public reproduction path and do not need local inference. | API key, network egress, model context length known. | Usually disabled. Remote providers already enforce admission. |
| Host-side `llama.cpp` | You have a single GPU host and GGUF models. | Host service reachable from pod, enough VRAM/RAM for model and KV cache, OpenAI-compatible server mode. | Recommended when only one local generation slot exists. |
| In-cluster model service | You run vLLM, llama.cpp, Ollama, or another OpenAI-compatible service in Kubernetes. | Service DNS, resource requests, storage for model artifacts. | Optional. Useful if the backend accepts oversized requests slowly. |
| Router/proxy service | You want route selection across local and remote models. | Stable OpenAI-compatible route and documented context per model. | Optional. The router may already provide admission and fallback. |

## Minimum Public Reproduction

For the public `deploy/k8s/examples/minimal` profile:

- Kubernetes node capacity: 2 CPU, 4 GiB memory for the Hermes gateway pod
- PVC: 20 GiB minimum
- model endpoint: external OpenAI-compatible API or a separately managed local
  service
- context length: 64K recommended; do not configure below Hermes's minimum
- TUI: image must include `ui-tui` and `tui_gateway`

This path does not require a GPU in Kubernetes if the model endpoint is remote
or host-managed.

## Local Inference Guidance

Local inference capacity depends on model size, quantization, context length,
KV cache type, backend, and concurrency. Treat these as starting points, not
guarantees:

For the node-a workstation profile, the current local routing decision is:

| Lane | Model | Why |
| --- | --- | --- |
| Primary 7900 XT workhorse | `gemma4-26b-a4b-it:q4km` | Best local Hermes quality score in the clean matrix: 67/81 overall and 29/30 agentic. |
| Fast local fallback | `qwen3.6-35b-a3b:iq4xs` | Much faster at 73.30 gen tok/s, but weaker quality: 56/81 and 20/30 agentic. |
| Qwen dense fallback | `qwen3.6-27b:q5ks-7900` | Qwen-family single-card comparison lane; not primary because it tied Qwen36 overall and trailed Gemma. |
| Split-card experiment | `qwen3.6-27b:q5ks-split` | Best split throughput found so far at 18.52 gen tok/s, but quality is pending and it touches the display GPU. |

Those quality scores come from the local Hermes benchmark suite under
`benchmark_runs/full_matrix_clean_20260423T2350Z/quality/`; they are not
community leaderboard scores.

| Tier | Example Use | Practical Notes |
| --- | --- | --- |
| CPU-only | Functional smoke tests with small models. | Slow for real agent work. Prefer a small model and shorter context. |
| 12-16 GiB GPU | Small/medium quantized models. | Good for testing the deployment loop, not ideal for long-context coding turns. |
| 24 GiB GPU | Larger quantized coding models with moderate context. | Tune batch size and KV cache; watch for context overflow. |
| 48 GiB+ GPU | Larger long-context local models. | Admission control becomes important when concurrency is low. |
| Remote API | Reproducible setup without local hardware. | Best public onboarding path; costs and rate limits move to provider. |

## Context Length Rules

Set `model.context_length` to the served context window, not the model's
marketing maximum and not a guessed lower value.

If configured too low, Hermes may reject the model before a turn starts. If
configured too high, the backend may fail after the prompt has already occupied
time and queue capacity.

For local backends:

1. Check backend model metadata or `/props` when available.
2. Confirm a small `/v1/chat/completions` request works.
3. Confirm a high-token prompt fails quickly or compacts through the admission
   path instead of hanging.
4. Record context length in the reproduction report.

## When To Disable The Admission Proxy

Disable the proxy when:

- using a robust external API provider
- using a router that already enforces context and rate admission
- running multiple backend replicas where one oversized request cannot block
  all useful traffic

Keep or add an admission proxy when:

- a single local model slot can be occupied for minutes
- overlarge requests time out instead of failing quickly
- you need consistent context-overflow telemetry
- you want Hermes to compact and retry from its own transcript state
