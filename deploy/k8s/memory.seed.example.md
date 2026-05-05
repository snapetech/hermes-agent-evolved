# Hermes Memory Seed Example

Use this as a public-safe starting point for `/opt/data/MEMORY.md`.

## Environment

- Kubernetes namespace: `hermes`
- Hermes home: `/opt/data`
- Workspace: `/opt/data/workspace`
- Model endpoint: operator-provided OpenAI-compatible `/v1`

## Operating Rules

- Keep prompt-visible memory short.
- Store private history, sessions, logs, and credentials only in runtime state.
- Promote reusable procedures into repo docs, skills, or sanitized seed files.
- Use branch/PR for code, lockfile, deployment, auth, RBAC, MCP, model-routing,
  memory/session, context-compression, or multi-file changes unless the
  operator explicitly approves otherwise.

## Private Data Boundary

Do not copy live user memories, transcripts, channel IDs, tokens, kubeconfigs,
SSH keys, auth mirrors, or workspace-specific facts into this seed.
