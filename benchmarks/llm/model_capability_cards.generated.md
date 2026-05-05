# Model Capability Cards

Generated from Hermes benchmark result JSON. Keep these cards focused on model routing decisions, not leaderboard claims.

## `qwen3.5-4b:q8`

- Overall: 36/81 (0.444), avg 2.81s/task
- Sources: /workspace/hermes-agent/benchmark_runs/full_matrix_clean_20260423T2315Z/quality/results_20260423_172010.json

| Task | Pass | Avg s | Verdict |
| --- | ---: | ---: | --- |
| workspace JSON composition | 2/3 | 11.12 | unstable |
| Discord status reply | 0/3 | 0.66 | failed |
| Discord triage reply | 0/3 | 0.53 | failed |
| logic consistency | 3/3 | 0.23 | candidate strength |
| structured logic JSON | 0/3 | 0.89 | failed |
| numeric instruction following | 0/3 | 1.51 | failed |
| JSON guard code fix | 0/3 | 5.62 | failed |
| small code patch | 3/3 | 6.73 | candidate strength |
| retry-after code fix | 3/3 | 5.42 | candidate strength |
| workspace config lookup | 3/3 | 4.27 | candidate strength |
| override config merge | 0/3 | 2.45 | failed |
| service command extraction | 0/3 | 1.01 | failed |
| short intent routing | 3/3 | 0.68 | candidate strength |
| mutation guard classification | 0/3 | 1.46 | exclude from approval/routing |
| Portuguese status summary | 3/3 | 0.55 | candidate strength |
| queue wait vs fallback decision | 0/3 | 0.72 | failed |
| Spanish status summary | 0/3 | 0.62 | failed |
| incident brief synthesis | 3/3 | 13.45 | candidate strength |
| file synthesis | 0/3 | 9.39 | failed |
| admission compaction decision | 3/3 | 0.99 | candidate strength |
| approval-risk labeling | 3/3 | 1.31 | candidate strength |
| operator-note extraction | 3/3 | 1.20 | candidate strength |
| failover lane selection | 0/3 | 1.40 | failed |
| short pulse condensation | 3/3 | 0.85 | candidate strength |
| read-only approval-risk labeling | 1/3 | 1.09 | exclude from approval/routing |
| restart cooldown decision | 0/3 | 1.03 | exclude from approval/routing |
| ops routing with approval flag | 0/3 | 0.68 | exclude from approval/routing |

- Good for: logic consistency, small code patch, retry-after code fix, workspace config lookup, short intent routing, Portuguese status summary, incident brief synthesis, admission compaction decision, approval-risk labeling, operator-note extraction, short pulse condensation.
- Do not use for: mutation guard classification, read-only approval-risk labeling, restart cooldown decision, ops routing with approval flag.
- Example failure signals:
  - workspace JSON composition -> I was unable to create the `/workspace/result.json` file. The terminal commands failed with a "Permission denied" error when attempting to create the `/workspace` directory. This indicates that the current user does not 
  - Discord status reply -> I've read incident.txt and found that the service "payment-gateway" was restarted to resolve the timeout issue.
  - Discord triage reply -> Recent.log shows a timeout failure that was recovered by restarting the service.
  - structured logic JSON -> {   "winner": "Blue",   "score": {     "Red": 4,     "Blue": 9,     "Green": 5   } }

## `qwen3.6-35b-a3b:iq4xs`

- Overall: 58/81 (0.716), avg 3.66s/task
- Sources: /workspace/hermes-agent/benchmark_runs/full_matrix_clean_20260423T2315Z/quality/results_20260423_171158.json

| Task | Pass | Avg s | Verdict |
| --- | ---: | ---: | --- |
| workspace JSON composition | 3/3 | 8.63 | candidate strength |
| Discord status reply | 3/3 | 4.07 | candidate strength |
| Discord triage reply | 0/3 | 1.02 | failed |
| logic consistency | 0/3 | 2.51 | failed |
| structured logic JSON | 3/3 | 0.46 | candidate strength |
| numeric instruction following | 0/3 | 0.37 | failed |
| JSON guard code fix | 3/3 | 6.46 | candidate strength |
| small code patch | 3/3 | 7.38 | candidate strength |
| retry-after code fix | 3/3 | 6.45 | candidate strength |
| workspace config lookup | 2/3 | 7.11 | unstable |
| override config merge | 0/3 | 12.06 | failed |
| service command extraction | 3/3 | 1.49 | candidate strength |
| short intent routing | 3/3 | 0.67 | candidate strength |
| mutation guard classification | 3/3 | 2.58 | candidate strength |
| Portuguese status summary | 2/3 | 0.73 | unstable |
| queue wait vs fallback decision | 2/3 | 0.70 | unstable |
| Spanish status summary | 3/3 | 0.87 | candidate strength |
| incident brief synthesis | 3/3 | 12.54 | candidate strength |
| file synthesis | 2/3 | 10.48 | unstable |
| admission compaction decision | 0/3 | 1.08 | failed |
| approval-risk labeling | 3/3 | 4.50 | candidate strength |
| operator-note extraction | 3/3 | 0.86 | candidate strength |
| failover lane selection | 0/3 | 1.42 | failed |
| short pulse condensation | 3/3 | 0.69 | candidate strength |
| read-only approval-risk labeling | 3/3 | 1.91 | candidate strength |
| restart cooldown decision | 3/3 | 1.09 | candidate strength |
| ops routing with approval flag | 2/3 | 0.67 | exclude from approval/routing |

- Good for: workspace JSON composition, Discord status reply, structured logic JSON, JSON guard code fix, small code patch, retry-after code fix, service command extraction, short intent routing, mutation guard classification, Spanish status summary, incident brief synthesis, approval-risk labeling, operator-note extraction, short pulse condensation, read-only approval-risk labeling, restart cooldown decision.
- Do not use for: ops routing with approval flag.
- Example failure signals:
  - Discord triage reply -> Service timed out on the upstream connection. Restarting the pod to recover.
  - logic consistency -> Ben
  - numeric instruction following -> 10
  - workspace config lookup -> The active API base URL is: `http://ollama.internal:11434/v1`
