# Keith Ops Policy

Use this skill when operating Keith's Hermes cluster, Kubernetes services, Git repositories, or long-lived agent runtime.

## Policy

- Prefer durable runtime fixes over repeated manual recovery.
- Do not run destructive Kubernetes, Helm, Terraform, database, or filesystem commands unless the user explicitly asked for that exact change.
- Use worktrees for parallel or risky code changes.
- Record important architectural decisions with `/decide` so future sessions can recover rationale, not just outcome.
- For cron and BOOT reconciliation, return `[SILENT]` when everything is healthy and only page the user for anomalies.
- Treat credentials, kubeconfigs, tokens, private hostnames, and secret-shaped strings as sensitive. Redact them from summaries.
- If a tool is blocked by runtime-control, narrow the command and ask for explicit approval rather than bypassing the guard.
